import os
import atexit
import warnings
import traceback
import threading

# -----------------------------------------------------------------------------
# Aggregated warning report (debounced + printed once)
# -----------------------------------------------------------------------------

_TENANCY_WARN_LOCK = threading.Lock()
_TENANCY_WARN_SEEN = set()    # set[(app_label, model_name, filename, lineno, funcname, line)]
_TENANCY_WARN_ITEMS = []      # list of dicts (stable order)
_TENANCY_REPORT_PRINTED = False

_TENANCY_DEBOUNCE_TIMER = None
_TENANCY_DEBOUNCE_SECONDS = 1.5  # print summary shortly after warnings stop


def _format_model_id(model):
    return f"{model._meta.app_label}.{model.__name__}"


def _find_trigger_frame():
    """
    Best-effort: find the first stack frame that is not inside the tenancy package,
    and not inside Django internals, so we land on user code.
    """
    stack = traceback.extract_stack()
    tenancy_dir = os.path.abspath(os.path.dirname(__file__))
    trigger = None

    for frame in reversed(stack):
        filename = os.path.abspath(frame.filename)

        # Skip frames inside tenancy package
        try:
            if os.path.commonpath([tenancy_dir, filename]) == tenancy_dir:
                continue
        except ValueError:
            pass

        # Skip Django internals
        if "site-packages" in filename and (os.sep + "django" + os.sep) in filename:
            continue

        trigger = frame
        break

    return trigger


def _build_summary_text(items):
    header = (
        "\n"
        "==================== TENANCY WARNING SUMMARY ====================\n"
        "Tenant was None while querying tenant-scoped models.\n"
        "These querysets were forced to .none() for safety.\n"
        "\n"
        "Unique triggers:\n"
    )

    body_lines = []
    for i, item in enumerate(items, start=1):
        body_lines.append(
            f"  {i}. {_format_model_id(item['model'])}\n"
            f"     {item['filename']}:{item['lineno']} in {item['funcname']}\n"
            f"     {item['line']}\n"
        )

    instructions = (
        "\n"
        "Canonical Django fixes:\n"
        "\n"
        "CASE 1: Explicit form fields declared at import time\n"
        "--------------------------------------------------\n"
        "  class MyForm(forms.Form):\n"
        "      person = forms.ModelChoiceField(queryset=Person.objects.none())\n"
        "\n"
        "      def __init__(self, *args, **kwargs):\n"
        "          super().__init__(*args, **kwargs)\n"
        "          self.fields['person'].queryset = Person.objects.all()\n"
        "\n"
        "CASE 2: ModelForm relationship fields (FK / M2M)\n"
        "--------------------------------------------------\n"
        "  class MyModelForm(forms.ModelForm):\n"
        "      related = forms.ModelChoiceField(\n"
        "          queryset=Person.objects.all_tenants().none()\n"
        "      )\n"
        "\n"
        "      class Meta:\n"
        "          model = MyModel\n"
        "          fields = ['related', ...]\n"
        "\n"
        "      def __init__(self, *args, **kwargs):\n"
        "          super().__init__(*args, **kwargs)\n"
        "          self.fields['related'].queryset = Person.objects.all()\n"
        "\n"
        "Explanation:\n"
        "  ModelForm auto-generates relationship fields at import time.\n"
        "  Overriding them with an EMPTY placeholder queryset prevents\n"
        "  tenant evaluation before runtime.\n"
        "===============================================================\n"
    )

    return header + "\n".join(body_lines) + instructions


def _print_summary_once():
    """
    Print the consolidated summary exactly once per process run.
    """
    global _TENANCY_REPORT_PRINTED

    with _TENANCY_WARN_LOCK:
        if _TENANCY_REPORT_PRINTED:
            return
        if not _TENANCY_WARN_ITEMS:
            return

        _TENANCY_REPORT_PRINTED = True
        text = _build_summary_text(_TENANCY_WARN_ITEMS)

    warnings.warn(text, RuntimeWarning, stacklevel=1)


def _schedule_debounced_summary():
    """
    Debounce printing so we emit one summary shortly after the flurry of warnings ends.
    """
    global _TENANCY_DEBOUNCE_TIMER

    def _timer_fn():
        # Print summary after debounce window
        _print_summary_once()

    # Cancel any existing pending timer and reschedule
    if _TENANCY_DEBOUNCE_TIMER is not None:
        try:
            _TENANCY_DEBOUNCE_TIMER.cancel()
        except Exception:
            pass

    _TENANCY_DEBOUNCE_TIMER = threading.Timer(_TENANCY_DEBOUNCE_SECONDS, _timer_fn)
    _TENANCY_DEBOUNCE_TIMER.daemon = True
    _TENANCY_DEBOUNCE_TIMER.start()


# Also print at process exit as a fallback
atexit.register(_print_summary_once)


def warn_missing_tenant(model):
    """
    Aggregate missing-tenant warnings and print a single summary shortly after startup.
    Still non-fatal; execution continues.
    """
    trigger = _find_trigger_frame()
    if trigger:
        filename = trigger.filename
        lineno = trigger.lineno
        funcname = trigger.name
        line = (trigger.line or "").strip()
    else:
        filename = "unknown"
        lineno = 0
        funcname = "unknown"
        line = ""

    key = (model._meta.app_label, model.__name__, filename, lineno, funcname, line)

    with _TENANCY_WARN_LOCK:
        if key in _TENANCY_WARN_SEEN:
            return

        _TENANCY_WARN_SEEN.add(key)
        _TENANCY_WARN_ITEMS.append(
            {
                "model": model,
                "filename": filename,
                "lineno": lineno,
                "funcname": funcname,
                "line": line,
            }
        )

        # Optional: short one-liner immediately for each new unique trigger
        warnings.warn(
            f"[tenancy warning] queued: {_format_model_id(model)} at {filename}:{lineno}",
            RuntimeWarning,
            stacklevel=2,
        )

        # Schedule one consolidated report soon
        _schedule_debounced_summary()
