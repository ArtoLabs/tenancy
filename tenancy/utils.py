"""
Utilities for cloning tenant-aware objects with foreign key relationships.

This module provides functionality to clone objects across multiple models
while respecting foreign key dependencies and maintaining referential integrity.

Supports three cloning modes:
1. Full clone (default) - Clone all field values normally
2. Skeleton clone - Clone the row but set all non-required fields to None
3. Field-level overrides - Clone with specific field values overridden
"""

import logging
from collections import defaultdict, deque
from typing import Dict, List, Optional, Any, Type, Set
from django.db import models, transaction
from django.apps import apps
from django.forms.models import model_to_dict


logger = logging.getLogger(__name__)


class CloneError(Exception):
    """Base exception for cloning operations."""
    pass


class CyclicDependencyError(CloneError):
    """Raised when a cyclic dependency is detected in the model graph."""
    pass


# ============================================================================
# MAIN CLONING FUNCTION
# ============================================================================

def clone_tenant_objects(
    querysets: Dict[Type[models.Model], models.QuerySet],
    new_tenant,
    field_overrides: Optional[Dict[Type[models.Model], Dict[str, Any]]] = None,
) -> Dict[Type[models.Model], Dict[int, models.Model]]:
    """
    Clone objects from multiple models in topological order, respecting FK dependencies.

    This function analyzes the foreign key relationships between models and clones
    them in the correct order so that when a model references another via FK, the
    referenced object has already been cloned and is available.

    Cloning Modes:
    --------------
    Models can define cloning behavior via class-level metadata:

    1. CLONE_MODE = 'full' (default)
       - Clone all field values normally
       - Foreign keys are resolved to newly cloned objects

    2. CLONE_MODE = 'skeleton'
       - Clone the row but set all nullable fields to None
       - Only required fields and tenant are set
       - Useful for creating blank configurations

    3. CLONE_FIELD_OVERRIDES = {'field_name': value, ...}
       - Clone with specific field values overridden
       - Takes precedence over CLONE_MODE
       - If both exist, CLONE_FIELD_OVERRIDES is used and a warning is logged

    Args:
        querysets: Dictionary mapping model classes to querysets of objects to clone.
                  Example: {Theme: Theme.objects.filter(tenant=template_tenant)}

        new_tenant: The target tenant instance for the cloned objects.

        field_overrides: Optional dictionary of field overrides per model.
                        These are applied AFTER model-level metadata.
                        Example: {
                            Theme: {'is_default': False},
                            Font: {'size': 12}
                        }

    Returns:
        Dictionary mapping model classes to dictionaries of old_id -> new_instance.
        Example: {
            Theme: {1: <Theme instance>, 2: <Theme instance>},
            Font: {1: <Font instance>}
        }

    Raises:
        CloneError: If cloning fails for any object
        CyclicDependencyError: If circular dependencies are detected

    Example:
        >>> from myapp.models import Theme, Font, SiteConfiguration
        >>>
        >>> # Get template objects
        >>> querysets = {
        ...     Font: Font.objects.filter(tenant=template_tenant),
        ...     Theme: Theme.objects.filter(tenant=template_tenant),
        ...     SiteConfiguration: SiteConfiguration.objects.filter(tenant=template_tenant),
        ... }
        >>>
        >>> # Clone for new tenant
        >>> new_tenant = Tenant.objects.get(id=5)
        >>> cloned_objects = clone_tenant_objects(querysets, new_tenant)
        >>>
        >>> # Access cloned objects
        >>> old_font_id = 10
        >>> new_font = cloned_objects[Font][old_font_id]
    """
    field_overrides = field_overrides or {}

    # Build dependency graph and perform topological sort
    models_to_clone = list(querysets.keys())
    sorted_models = _topological_sort_models(models_to_clone)

    logger.info(f"Cloning models in order: {[m.__name__ for m in sorted_models]}")

    # Store mapping of old object IDs to new cloned instances
    # Structure: {Model: {old_id: new_instance}}
    clone_map: Dict[Type[models.Model], Dict[int, models.Model]] = defaultdict(dict)

    with transaction.atomic():
        # Clone models in topological order
        for model in sorted_models:
            if model not in querysets:
                # Skip models that weren't requested for cloning
                continue

            clone_mode = _get_clone_mode(model)
            if clone_mode == 'none':
                logger.info(f"Skipping {model.__name__} - CLONE_MODE='none'")
                continue

            queryset = querysets[model]
            overrides = field_overrides.get(model, {})

            # Check and log cloning mode for this model
            clone_mode = _get_clone_mode(model)
            logger.info(
                f"Cloning {queryset.count()} objects for {model.__name__} "
                f"using mode: {clone_mode}"
            )

            for original_obj in queryset:
                try:
                    # Clone the object and store the mapping
                    new_obj = _clone_single_object(
                        original_obj,
                        new_tenant,
                        clone_map,
                        overrides
                    )
                    clone_map[model][original_obj.id] = new_obj

                except Exception as e:
                    logger.error(
                        f"Failed to clone {model.__name__} with id={original_obj.id}: {e}"
                    )
                    raise CloneError(
                        f"Failed to clone {model.__name__} (id={original_obj.id})"
                    ) from e

    logger.info(f"Successfully cloned objects across {len(clone_map)} models")
    return dict(clone_map)


# ============================================================================
# SINGLE OBJECT CLONING WITH MODE SUPPORT
# ============================================================================

def _clone_single_object(
    original_obj: models.Model,
    new_tenant,
    clone_map: Dict[Type[models.Model], Dict[int, models.Model]],
    field_overrides: Dict[str, Any],
) -> models.Model:
    """
    Clone a single object, respecting the model's cloning mode and metadata.

    This function implements the core cloning logic:
    1. Determines the cloning mode from model metadata
    2. Extracts field values based on the mode
    3. Resolves foreign key references from the clone map
    4. Applies field overrides
    5. Sets the new tenant
    6. Creates and returns the new object

    Cloning Mode Logic:
    -------------------
    - If CLONE_FIELD_OVERRIDES exists: use field-level overrides (precedence)
    - Else if CLONE_MODE == 'skeleton': set all nullable fields to None
    - Else: full clone (default behavior)

    Args:
        original_obj: The object to clone
        new_tenant: The target tenant for the clone
        clone_map: Map of already cloned objects to resolve FK references
        field_overrides: Field values to override in the clone (applied last)

    Returns:
        The newly created cloned object
    """
    model_class = original_obj.__class__

    # Get exclude fields from the model or use defaults
    exclude_fields = getattr(model_class, 'CLONE_EXCLUDE_FIELDS', ('id', 'pk'))

    # Determine cloning mode and check for metadata conflicts
    has_field_overrides = hasattr(model_class, 'CLONE_FIELD_OVERRIDES')
    has_clone_mode = hasattr(model_class, 'CLONE_MODE')

    # Warn if both metadata types exist
    if has_field_overrides and has_clone_mode:
        logger.warning(
            f"{model_class.__name__}: Both CLONE_MODE and CLONE_FIELD_OVERRIDES "
            f"are defined. CLONE_FIELD_OVERRIDES takes precedence. "
            f"CLONE_MODE='{model_class.CLONE_MODE}' is being IGNORED."
        )
        print(
            f"⚠️  WARNING: {model_class.__name__} has both CLONE_MODE and "
            f"CLONE_FIELD_OVERRIDES defined. Using CLONE_FIELD_OVERRIDES only."
        )

    # Extract field data based on cloning mode
    if has_field_overrides:
        # Mode 3: Field-level overrides
        data = _extract_fields_with_model_overrides(
            original_obj,
            exclude_fields,
            model_class.CLONE_FIELD_OVERRIDES
        )
        logger.debug(
            f"Using CLONE_FIELD_OVERRIDES for {model_class.__name__}: "
            f"{model_class.CLONE_FIELD_OVERRIDES}"
        )
    elif has_clone_mode and model_class.CLONE_MODE == 'skeleton':
        # Mode 2: Skeleton clone
        data = _extract_fields_skeleton_mode(original_obj, exclude_fields)
        logger.debug(f"Using skeleton mode for {model_class.__name__}")
    else:
        # Mode 1: Full clone (default)
        data = model_to_dict(original_obj, exclude=exclude_fields)
        logger.debug(f"Using full clone mode for {model_class.__name__}")

    # Process foreign key fields - resolve references to cloned objects
    # This happens AFTER initial extraction but BEFORE overrides
    data = _resolve_foreign_keys(
        original_obj,
        model_class,
        data,
        clone_map,
        skip_fk_resolution=(has_field_overrides or
                           (has_clone_mode and model_class.CLONE_MODE == 'skeleton'))
    )

    # Set the new tenant
    data['tenant'] = new_tenant

    # Apply any runtime field overrides (these override everything)
    data.update(field_overrides)

    # Create the new object
    new_obj = model_class.objects.create(**data)

    logger.debug(
        f"Cloned {model_class.__name__}(id={original_obj.id}) -> (id={new_obj.id})"
    )

    return new_obj


# ============================================================================
# FIELD EXTRACTION HELPERS
# ============================================================================

def _extract_fields_with_model_overrides(
    original_obj: models.Model,
    exclude_fields: tuple,
    clone_field_overrides: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Extract fields and apply model-level CLONE_FIELD_OVERRIDES.

    This mode clones the object normally but overrides specific fields
    as defined in the model's CLONE_FIELD_OVERRIDES dictionary.

    Args:
        original_obj: The object to clone
        exclude_fields: Fields to exclude from extraction
        clone_field_overrides: Dictionary of field name -> value overrides

    Returns:
        Dictionary of field values with overrides applied
    """
    # Start with full clone
    data = model_to_dict(original_obj, exclude=exclude_fields)

    # Apply model-level overrides
    for field_name, override_value in clone_field_overrides.items():
        data[field_name] = override_value
        logger.debug(
            f"Override {original_obj.__class__.__name__}.{field_name} = {override_value}"
        )

    return data


def _extract_fields_skeleton_mode(
    original_obj: models.Model,
    exclude_fields: tuple
) -> Dict[str, Any]:
    """
    Extract fields in skeleton mode - set fields to sensible defaults.

    In skeleton mode:
    - Required fields are cloned from the original
    - Optional fields get intelligent defaults based on field type:
      * CharField/TextField → empty string ""
      * IntegerField/FloatField/DecimalField → 0
      * BooleanField → False
      * DateField/DateTimeField → None
      * ForeignKey → first available instance of related model, or None
      * Other fields → None
    - If a field already has a default value defined, that default is used

    This creates functional "blank" objects that won't cause __str__ issues
    and can be immediately used/edited by users.

    Args:
        original_obj: The object to clone
        exclude_fields: Fields to exclude from extraction

    Returns:
        Dictionary of field values with intelligent skeleton defaults
    """
    model_class = original_obj.__class__
    data = {}

    for field in model_class._meta.get_fields():
        # Skip excluded fields, reverse relations, and many-to-many
        if (field.name in exclude_fields or
            not hasattr(field, 'get_attname') or
            field.many_to_many):
            continue

        field_name = field.name

        # Skip tenant field (handled separately)
        if field_name == 'tenant':
            continue

        # Determine if field is required
        is_required = not field.null and not field.has_default()

        if is_required:
            # Keep required field values
            data[field_name] = getattr(original_obj, field_name)
            logger.debug(
                f"Skeleton mode: keeping required field "
                f"{model_class.__name__}.{field_name}"
            )
        else:
            # Set optional fields to intelligent defaults
            default_value = _get_skeleton_default_for_field(field)
            data[field_name] = default_value
            logger.debug(
                f"Skeleton mode: setting {model_class.__name__}.{field_name} "
                f"to {default_value} (type: {type(field).__name__})"
            )

    return data


def _get_skeleton_default_for_field(field) -> Any:
    """
    Get an intelligent default value for a field in skeleton clone mode.

    This function determines appropriate "blank" values based on field type
    to ensure cloned skeleton objects are functional and don't cause issues
    with __str__ methods or validation.

    Priority:
    1. If field has a default value defined, use it
    2. Otherwise, use type-based intelligent defaults

    Args:
        field: Django model field instance

    Returns:
        Appropriate default value for the field type
    """
    # If field has an explicit default, use it
    if field.has_default():
        default = field.get_default()
        logger.debug(f"Using field default: {default}")
        return default

    # String fields - use empty string to prevent None in __str__
    if isinstance(field, (models.CharField, models.TextField,
                         models.SlugField, models.EmailField,
                         models.URLField)):
        return ""

    # Numeric fields - use 0
    if isinstance(field, (models.IntegerField, models.BigIntegerField,
                         models.SmallIntegerField, models.PositiveIntegerField,
                         models.PositiveSmallIntegerField)):
        return 0

    if isinstance(field, (models.FloatField, models.DecimalField)):
        return 0

    # Boolean fields - use False
    if isinstance(field, models.BooleanField):
        return False

    # Foreign Key - try to find first available instance
    if isinstance(field, models.ForeignKey):
        try:
            related_model = field.related_model
            # Try to get the first instance of the related model
            first_instance = related_model.objects.first()
            if first_instance:
                logger.debug(
                    f"Found first instance of {related_model.__name__} "
                    f"(id={first_instance.id}) for FK default"
                )
                return first_instance
        except Exception as e:
            logger.warning(
                f"Could not get first instance for FK field {field.name}: {e}"
            )
        return None

    # Date/Time fields - use None (these typically shouldn't be empty string)
    if isinstance(field, (models.DateField, models.DateTimeField,
                         models.TimeField)):
        return None

    # JSON fields - use empty dict or list
    if isinstance(field, models.JSONField):
        return {}

    # All other field types - use None
    return None


def _resolve_foreign_keys(
    original_obj: models.Model,
    model_class: Type[models.Model],
    data: Dict[str, Any],
    clone_map: Dict[Type[models.Model], Dict[int, models.Model]],
    skip_fk_resolution: bool = False
) -> Dict[str, Any]:
    """
    Resolve foreign key fields to point to newly cloned objects.

    For each FK field:
    1. Check if the related object has been cloned
    2. If yes, update the FK to point to the cloned instance
    3. If no, keep the original FK (with warning)

    Args:
        original_obj: The original object being cloned
        model_class: The model class
        data: Dictionary of field values (will be modified)
        clone_map: Map of cloned objects
        skip_fk_resolution: If True, don't resolve FKs (for skeleton/override modes)

    Returns:
        Updated data dictionary with resolved FKs
    """
    try:
        all_fields = model_class._meta.get_fields()
    except Exception as e:
        logger.error(f"Error getting fields for {model_class.__name__}: {e}")
        return data

    for field in all_fields:
        # Check if this is a ForeignKey field
        try:
            if not isinstance(field, models.ForeignKey):
                continue
        except Exception as e:
            logger.warning(
                f"Skipping field in {model_class.__name__} during FK resolution: {e}. "
                f"Field type: {type(field)}"
            )
            continue

        field_name = field.name

        # Skip the tenant field - handled separately
        if field_name == 'tenant':
            continue

        # If using skeleton mode or field overrides, skip FK resolution
        # (fields are already set to None or override values)
        if skip_fk_resolution:
            continue

        # Get the original related object ID
        try:
            original_fk_id = getattr(original_obj, f"{field_name}_id", None)
        except Exception as e:
            logger.warning(f"Could not get FK ID for {field_name}: {e}")
            continue

        if original_fk_id is None:
            # FK is null, keep it null
            data[field_name] = None
            continue

        # Get the related model
        try:
            related_model = field.related_model
        except Exception as e:
            logger.warning(f"Could not get related_model for {field_name}: {e}")
            continue

        # Check if we've already cloned this related object
        if related_model in clone_map and original_fk_id in clone_map[related_model]:
            # Use the cloned instance
            data[field_name] = clone_map[related_model][original_fk_id]
            logger.debug(
                f"Resolved FK {field_name} for {model_class.__name__}: "
                f"{original_fk_id} -> {data[field_name].id}"
            )
        else:
            # Related object hasn't been cloned yet
            # This shouldn't happen if topological sort worked correctly
            logger.warning(
                f"FK {field_name} references {related_model.__name__}(id={original_fk_id}) "
                f"which hasn't been cloned yet. This may indicate a missing dependency "
                f"or the related object wasn't included in the cloning queryset."
            )
            # Keep the original FK value - this may cause issues if the
            # referenced object doesn't exist in the new tenant
            try:
                data[field_name] = getattr(original_obj, field_name)
            except Exception as e:
                logger.error(f"Could not get original FK value for {field_name}: {e}")
                data[field_name] = None

    return data


def _get_clone_mode(model_class: Type[models.Model]) -> str:
    """
    Get the cloning mode for a model as a human-readable string.

    Args:
        model_class: The model class to check

    Returns:
        String describing the clone mode: 'field_overrides', 'skeleton', or 'full'
    """
    if hasattr(model_class, 'CLONE_FIELD_OVERRIDES'):
        return 'field_overrides'
    elif hasattr(model_class, 'CLONE_MODE'):
        return model_class.CLONE_MODE
    else:
        return 'full'


# ============================================================================
# TOPOLOGICAL SORTING FOR DEPENDENCY RESOLUTION
# ============================================================================

def _topological_sort_models(
    models_list: List[Type[models.Model]]
) -> List[Type[models.Model]]:
    """
    Sort models in topological order based on foreign key dependencies.

    Models with no dependencies come first, followed by models that depend on them.
    This ensures that when we clone objects, any foreign key references point to
    objects that have already been cloned.

    Args:
        models: List of Django model classes to sort

    Returns:
        List of models sorted in topological order (dependencies first)

    Raises:
        CyclicDependencyError: If circular dependencies exist

    Algorithm:
        Uses Kahn's algorithm for topological sorting:
        1. Build adjacency list and calculate in-degrees
        2. Start with models that have no dependencies (in-degree = 0)
        3. Process each model, removing edges and updating in-degrees
        4. If we can't process all models, there's a cycle

    Example:
        If Font has no FKs, Theme references Font, and SiteConfig references Theme:
        Result: [Font, Theme, SiteConfig]
    """
    # Build dependency graph
    # graph[model] = list of models that depend on 'model'
    graph = defaultdict(list)

    # Count of dependencies for each model
    in_degree = defaultdict(int)

    # Initialize all models with 0 in-degree
    for model in models_list:
        in_degree[model] = 0

    # Build the graph by examining foreign key relationships
    for model in models_list:
        try:
            # Get all fields for this model
            all_fields = model._meta.get_fields()
        except Exception as e:
            logger.error(f"Error getting fields for {model.__name__}: {e}")
            continue

        for field in all_fields:
            # Skip fields that aren't ForeignKey instances
            # Use try-except to handle any edge cases
            try:
                if not isinstance(field, models.ForeignKey):
                    continue
            except Exception as e:
                logger.warning(
                    f"Skipping field in {model.__name__} due to error: {e}. "
                    f"Field type: {type(field)}"
                )
                continue

            # Skip self-referential and tenant FKs
            try:
                related_model = field.related_model
            except Exception as e:
                logger.warning(f"Could not get related_model for field {field.name}: {e}")
                continue

            if related_model == model or field.name == 'tenant':
                continue

            # Only consider relationships between models we're cloning
            if related_model not in models:
                continue

            # model depends on related_model
            # So related_model must be cloned before model
            graph[related_model].append(model)
            in_degree[model] += 1

    # Find all models with no dependencies
    queue = deque([model for model in models_list if in_degree[model] == 0])
    sorted_models = []

    # Process models in topological order
    while queue:
        # Take a model with no remaining dependencies
        current = queue.popleft()
        sorted_models.append(current)

        # Remove edges from current to its dependents
        for dependent in graph[current]:
            in_degree[dependent] -= 1

            # If dependent now has no dependencies, add it to queue
            if in_degree[dependent] == 0:
                queue.append(dependent)

    # Check if we processed all models
    if len(sorted_models) != len(models_list):
        # There's a cycle - find which models are involved
        remaining = set(models_list) - set(sorted_models)
        raise CyclicDependencyError(
            f"Cyclic dependency detected between models: "
            f"{[m.__name__ for m in remaining]}"
        )

    return sorted_models


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def get_all_tenant_models() -> List[Type[models.Model]]:
    """
    Get all models that use TenantMixin.

    Returns:
        List of concrete (non-abstract) model classes that have a 'tenant' field

    Example:
        >>> tenant_models = get_all_tenant_models()
        >>> for model in tenant_models:
        ...     print(f"Found tenant model: {model.__name__}")
    """
    tenant_models = []

    for model in apps.get_models():
        # Skip abstract models
        if model._meta.abstract:
            continue

        # Check if model has a tenant field (i.e., uses TenantMixin)
        if hasattr(model, '_is_tenant_model') and model._is_tenant_model():
            tenant_models.append(model)
            logger.debug(f"Found tenant model: {model.__name__}")

    return tenant_models


def clone_all_template_objects(
    new_tenant,
    template_tenant=None,
    excluded_models: Optional[List[Type[models.Model]]] = None,
    field_overrides: Optional[Dict[Type[models.Model], Dict[str, Any]]] = None,
) -> Dict[Type[models.Model], Dict[int, models.Model]]:
    """
    Convenience function to clone all template objects for a new tenant.

    This function automatically:
    1. Discovers all models using TenantMixin
    2. Gets template objects from each model
    3. Respects each model's cloning mode (CLONE_MODE or CLONE_FIELD_OVERRIDES)
    4. Clones them in the correct topological order

    Args:
        new_tenant: The target tenant for cloned objects
        template_tenant: The template tenant to clone from (default: first tenant)
        excluded_models: List of models to skip cloning
        field_overrides: Runtime field overrides per model (applied after model metadata)

    Returns:
        Dictionary mapping model classes to clone mappings

    Example:
        >>> new_tenant = Tenant.objects.create(name="New Tenant", domain="new.example.com")
        >>>
        >>> # Clone all with default modes
        >>> cloned = clone_all_template_objects(new_tenant)
        >>>
        >>> # Or with runtime overrides
        >>> cloned = clone_all_template_objects(
        ...     new_tenant,
        ...     field_overrides={
        ...         SiteConfiguration: {'is_default': True}
        ...     }
        ... )
        >>> print(f"Cloned objects from {len(cloned)} models")
    """
    excluded_models = excluded_models or []

    # Get template tenant if not provided
    if template_tenant is None:
        from .models import Tenant
        template_tenant = Tenant.objects.order_by("id").first()
        if template_tenant is None:
            logger.warning("No template tenant found, nothing to clone")
            return {}

    # Build querysets for all tenant models
    querysets = {}
    tenant_models = get_all_tenant_models()

    # DEBUG: Log field information for all models
    logger.debug("=" * 60)
    logger.debug("DEBUG: Examining fields for all tenant models")
    logger.debug("=" * 60)
    for model in tenant_models:
        logger.debug(f"\n{model.__name__} fields:")
        try:
            all_fields = model._meta.get_fields()
            for field in all_fields:
                logger.debug(
                    f"  - {getattr(field, 'name', 'NO_NAME')}: {type(field)} "
                    f"(is FK: {isinstance(field, models.ForeignKey)})"
                )
        except Exception as e:
            logger.error(f"  ERROR getting fields for {model.__name__}: {e}")
    logger.debug("=" * 60)

    for model in tenant_models:
        if model in excluded_models:
            logger.info(f"Skipping excluded model: {model.__name__}")
            continue

        # Get template objects for this model
        if hasattr(model, 'get_template_queryset'):
            qs = model.get_template_queryset()
        else:
            qs = model.objects.filter(tenant=template_tenant)

        if qs.exists():
            querysets[model] = qs
            clone_mode = _get_clone_mode(model)
            logger.info(
                f"Found {qs.count()} template objects for {model.__name__} "
                f"(mode: {clone_mode})"
            )

    if not querysets:
        logger.info("No template objects found to clone")
        return {}

    # Clone all objects
    return clone_tenant_objects(querysets, new_tenant, field_overrides)