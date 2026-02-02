import os
import atexit
import warnings
import traceback
import threading

# -----------------------------------------------------------------------------
# Aggregated warning report (printed once)
# -----------------------------------------------------------------------------

_TENANCY_WARN_LOCK = threading.Lock()
_TENANCY_WARN_SEEN = set()   # set[(app_label, model_name, filename, lineno, funcname, line)]
_TENANCY_WARN_ITEMS = []     # list of dicts for stable print order
_TENANCY_WARN_REPORT_REGISTERED = False


def _format_model_id(model):
    return f"{model._meta.app_label}.{model.__name__}"


def _find_trigger_frame():
    """
    Best-effort: find the first stack frame that is not inside the tenancy package,
    and (optionally) not inside Django internals.
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
            # Different drives on Windows etc.
            pass

        # Skip Django internals to land on user code more often
        if "site-packages" in filename and (os.sep + "django" + os.sep) in filename:
            continue

        trigger = frame
        break

    return trigger


def _register_tenancy_report_once():
    global _TENANCY_WARN_REPORT_REGISTERED
    if _TENANCY_WARN_REPORT_REGISTERED:
        return

    def _print_report():
        with _TENANCY_WARN_LOCK:
            if not _TENANCY_WARN_ITEMS:
                return

            header = (
                "\n"
                "==================== TENANCY WARNING SUMMARY ====================\n"
                "Tenant was None while querying tenant-scoped models.\n"
                "These querysets were forced to .none() for safety.\n"
                "\n"
                "Unique triggers:\n"
            )
            body_lines = []
            for i, item in enumerate(_TENANCY_WARN_ITEMS, start=1):
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

            warnings.warn(header + "\n".join(body_lines) + instructions, RuntimeWarning, stacklevel=1)

    atexit.register(_print_report)
    _TENANCY_WARN_REPORT_REGISTERED = True


def warn_missing_tenant(model):
    """
    Aggregate missing-tenant warnings and print a single summary at process exit.
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
        _register_tenancy_report_once()

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

        # Optional: print a short, non-spammy one-liner immediately for new triggers.
        warnings.warn(
            f"[tenancy warning] queued: {_format_model_id(model)} at {filename}:{lineno}",
            RuntimeWarning,
            stacklevel=2,
        )
