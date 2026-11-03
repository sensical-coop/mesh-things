"""drf-spectacular hooks for the registry's schema."""

from .serializers import DeviceReadSerializer, MeshSerializer

# Response components whose serializer leaves fields out for viewers other than the
# mesh owner and superusers. drf-spectacular marks every read-only field as required.
_OWNER_ONLY_FIELDS = {
    "DeviceRead": DeviceReadSerializer.owner_only_fields,
    "Mesh": MeshSerializer.owner_only_fields,
}


def owner_only_fields_optional(result, generator, request, public):
    """Leave the fields only a mesh's owner receives out of each response's `required`."""
    schemas = result.get("components", {}).get("schemas", {})
    for name, fields in _OWNER_ONLY_FIELDS.items():
        component = schemas.get(name)
        if component is None:
            continue
        required = [field for field in component.get("required", []) if field not in fields]
        if required:
            component["required"] = required
        else:
            component.pop("required", None)
    return result
