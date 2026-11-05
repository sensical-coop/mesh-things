"""Data-migration steps for retiring a protocol version.

Retiring one takes two releases. The first, while the version still ships, moves its
meshes up with `move_meshes_off`, which refuses unless the next version only adds
fields; `manage.py publish_gateways` then sends the decoder the new version. The release
that deletes the version's generated set adds `refuse_while_used`, so it cannot be
applied while a mesh is still on it.
"""
from mesh_things import protocols


def move_meshes_off(version: str):
    """A RunPython function moving every mesh on `version` to the next version."""

    def run(apps, schema_editor):
        if not protocols.can_move_up(version):
            raise RuntimeError(
                f"Meshes on protocol {version} cannot be moved automatically: the next version is "
                f"not declared adds_only. Their owners have to move them first."
            )
        target = protocols.newer_than(version)[0]
        apps.get_model("registry", "Mesh").objects.filter(protocol=version).update(protocol=target)

    return run


def refuse_while_used(version: str):
    """A RunPython function that fails while any mesh is still declared on `version`."""

    def run(apps, schema_editor):
        left = apps.get_model("registry", "Mesh").objects.filter(protocol=version).count()
        if left:
            raise RuntimeError(f"{left} mesh(es) are still on protocol {version}; move them before removing it.")

    return run
