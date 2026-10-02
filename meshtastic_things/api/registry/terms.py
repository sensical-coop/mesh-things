"""The terms owners accept: account terms at signup, mesh terms per default-broker mesh,
and source terms per source.

A version and its text change together: any edit to a statement needs a new version,
so that each acceptance's `text_hash` still names the text it agreed to. The retention
sentence of the mesh and source terms, and the address of the Data Processing Agreement
they point to, are built from the settings, so changing them changes the hash too.
"""
import hashlib
import json

from django.conf import settings
from django.utils import timezone

from .models import TermsKind

DEFAULT_LOCALE = "en"
LOCALES = ("en", "es")

VERSIONS = {
    TermsKind.ACCOUNT: "account-2026-10",
    TermsKind.MESH: "meshes-2026-10",
    TermsKind.SOURCE: "sources-2026-10",
}

# The console mock (apps/api-mock/src/features/terms/terms.ts) carries a copy of this text
# and must be kept in step. Draft wording pending the legal review listed in plans/01a-mqtt-sources.md.
_ACCOUNT = {
    "en": {
        "title": "Before you create your account",
        "description": (
            "Your account lets you sign in, explore public meshes and manage your profile. It "
            "stores only your name, email address and settings. Creating a mesh, which stores data "
            "from its devices, asks you to accept its own terms at that point."
        ),
        "statements": [
            ("terms", "I accept the Mesh Things Terms of Use."),
            ("privacy", "I've read the Privacy Policy, which explains how my name and email address are used."),
        ],
        "footnote": (
            "You can delete your account at any time from your profile. Questions or data requests: "
            "info@sensical.es."
        ),
    },
    "es": {
        "title": "Antes de crear tu cuenta",
        "description": (
            "Tu cuenta te permite iniciar sesión, explorar mallas públicas y gestionar tu perfil. Solo "
            "guarda tu nombre, tu correo y tus ajustes. Crear una malla, que guarda los datos de sus "
            "dispositivos, te pide aceptar sus propias condiciones en ese momento."
        ),
        "statements": [
            ("terms", "Acepto las Condiciones de uso de Mesh Things."),
            ("privacy", "He leído la Política de privacidad, que explica cómo se usan mi nombre y mi correo."),
        ],
        "footnote": (
            "Puedes eliminar tu cuenta cuando quieras desde tu perfil. Dudas o solicitudes sobre datos: "
            "info@sensical.es."
        ),
    },
}

_MESH = {
    "en": {
        "title": "Before you create a mesh",
        "description": (
            "A mesh stores the traffic its gateways send to the default broker. That traffic can "
            "include personal data from people who never signed up here: node names, device IDs, "
            "positions and telemetry. For this mesh you decide what is collected and why, "
            "and Sensical processes it only on your behalf to run the service. Tick each box to "
            "continue."
        ),
        "statements": [
            (
                "controller",
                "I act as data controller for the traffic this mesh brings in. I authorise Sensical to "
                "ingest, decode and store it on my behalf as a processor, under the Data Processing "
                "Agreement ({dpa_url}). "
                "If I'm an operator, this includes keeping the devices I choose in a long-term archive "
                "that I can download.",
            ),
            (
                "lawfulBasis",
                "I have a lawful basis for this processing, such as legitimate interest, and I tell the "
                "people whose nodes appear on this mesh how their data is used.",
            ),
            (
                "minimisation",
                "I'll store only what this mesh needs: I'll register only its own gateways and, if I "
                "archive devices, only those I need and only while I need them.",
            ),
            (
                "sensitive",
                "I won't use this mesh to collect sensitive data, such as health information, or to "
                "track or profile individuals.",
            ),
        ],
        "footnote": (
            "You can withdraw at any time by deleting the mesh. Questions or data requests: "
            "info@sensical.es."
        ),
        "retention_limited": (
            "This acceptance is valid for {days} days. We'll email you before it lapses so you can "
            "renew it. If you don't, the mesh stops storing new data, and the data it stored, "
            "including any archive, is deleted {grace} days later unless you renew in the meantime."
        ),
        "retention_unlimited": (
            "The mesh's data is kept while the mesh is in use. When you delete it, its data, "
            "including any archive, is deleted {grace} days later."
        ),
    },
    "es": {
        "title": "Antes de crear una malla",
        "description": (
            "Una malla guarda el tráfico que sus pasarelas envían al bróker por defecto. Ese tráfico "
            "puede incluir datos personales de personas que nunca se han registrado aquí: nombres de "
            "nodo, identificadores de dispositivo, posiciones y telemetría. En esta malla tú "
            "decides qué se recoge y para qué, y Sensical lo trata solo por tu cuenta para prestar el "
            "servicio. Marca cada casilla para continuar."
        ),
        "statements": [
            (
                "controller",
                "Actúo como responsable del tratamiento del tráfico que trae esta malla. Autorizo a "
                "Sensical a recibirlo, descifrarlo y almacenarlo por mi cuenta como encargado del "
                "tratamiento, según el Acuerdo de procesamiento de los datos ({dpa_url}). Si soy operador, "
                "esto incluye "
                "conservar los dispositivos que elija en un archivo a largo plazo que puedo descargar.",
            ),
            (
                "lawfulBasis",
                "Tengo una base jurídica para este tratamiento, como el interés legítimo, e informo a las "
                "personas cuyos nodos aparecen en esta malla de cómo se usan sus datos.",
            ),
            (
                "minimisation",
                "Guardaré solo lo que esta malla necesite: registraré solo sus propias pasarelas y, si "
                "archivo dispositivos, solo los que necesite y solo mientras los necesite.",
            ),
            (
                "sensitive",
                "No usaré esta malla para recoger datos sensibles, como información de salud, ni para "
                "seguir o perfilar a personas.",
            ),
        ],
        "footnote": (
            "Puedes retirarte cuando quieras eliminando la malla. Dudas o solicitudes sobre datos: "
            "info@sensical.es."
        ),
        "retention_limited": (
            "Esta aceptación es válida durante {days} días. Te avisaremos por correo antes de que "
            "caduque para que puedas renovarla. Si no lo haces, la malla deja de guardar datos nuevos, "
            "y los datos guardados, incluido cualquier archivo, se borran {grace} días después salvo "
            "que renueves antes."
        ),
        "retention_unlimited": (
            "Los datos de la malla se conservan mientras la malla esté en uso. Cuando la eliminas, sus "
            "datos, incluido cualquier archivo, se borran {grace} días después."
        ),
    },
}

# Settled with the console. The operator is the controller of the bridged traffic and
# Sensical its processor.
_SOURCE = {
    "en": {
        "title": "Before you connect a source",
        "description": (
            "A source bridges traffic from a broker you choose into Mesh Things. That traffic can "
            "include personal data from people who never signed up here: node names, device IDs, "
            "positions and telemetry. For this traffic you decide what is collected and "
            "why, and Sensical processes it only on your behalf to run the service. Tick each box "
            "to continue."
        ),
        "statements": [
            (
                "controller",
                "I act as data controller for the traffic this source brings in. I authorise "
                "Sensical to ingest, decode and store it on my behalf as a processor, under the "
                "Data Processing Agreement ({dpa_url}). This includes keeping the devices I choose in a "
                "long-term archive "
                "that I can download.",
            ),
            (
                "authority",
                "I'm authorised to use this broker, its credentials and the mesh's encryption key, "
                "and bridging this traffic doesn't break the broker's or the channel's rules.",
            ),
            (
                "lawfulBasis",
                "I have a lawful basis for this processing, such as legitimate interest, and I tell "
                "the people whose nodes appear on this channel how their data is used.",
            ),
            (
                "minimisation",
                "I'll use the narrowest topic filter that covers my mesh, I won't bridge traffic I "
                "don't need, and I'll archive only the devices I need and only while I need them.",
            ),
            (
                "sensitive",
                "I won't use this source to collect sensitive data, such as health information, or "
                "to track or profile individuals.",
            ),
        ],
        "footnote": (
            "You can withdraw at any time: delete the source's meshes, then the source, and the "
            "bridge stops. Questions or data requests: info@sensical.es."
        ),
        "retention_limited": (
            "This acceptance is valid for {days} days. We'll email you before it lapses so you can "
            "renew it. If you don't, the source is paused, and the data of its meshes, including "
            "any archive, is deleted {grace} days later unless you renew in the meantime."
        ),
        "retention_unlimited": (
            "Data from this source is kept while the source is in use. When a mesh is deleted or "
            "moved off the source, its data, including any archive, is deleted {grace} days later."
        ),
    },
    "es": {
        "title": "Antes de conectar una fuente",
        "description": (
            "Una fuente trae a Mesh Things el tráfico de un bróker que tú eliges. Ese tráfico puede "
            "incluir datos personales de personas que nunca se han registrado aquí: nombres de "
            "nodo, identificadores de dispositivo, posiciones y telemetría. En este "
            "tráfico tú decides qué se recoge y para qué, y Sensical lo trata solo por tu cuenta "
            "para prestar el servicio. Marca cada casilla para continuar."
        ),
        "statements": [
            (
                "controller",
                "Actúo como responsable del tratamiento del tráfico que trae esta fuente. Autorizo a "
                "Sensical a recibirlo, descifrarlo y almacenarlo por mi cuenta como encargado del "
                "tratamiento, según el Acuerdo de procesamiento de los datos ({dpa_url}). Esto incluye "
                "conservar los "
                "dispositivos que elija en un archivo a largo plazo que puedo descargar.",
            ),
            (
                "authority",
                "Estoy autorizado a usar este bróker, sus credenciales y la clave de cifrado de la "
                "malla, y traer este tráfico no incumple las normas del bróker ni del canal.",
            ),
            (
                "lawfulBasis",
                "Tengo una base jurídica para este tratamiento, como el interés legítimo, e informo a "
                "las personas cuyos nodos aparecen en este canal de cómo se usan sus datos.",
            ),
            (
                "minimisation",
                "Usaré el filtro de tema más estrecho que cubra mi malla, no traeré tráfico que no "
                "necesite y archivaré solo los dispositivos que necesite y solo mientras los necesite.",
            ),
            (
                "sensitive",
                "No usaré esta fuente para recoger datos sensibles, como información de salud, ni "
                "para seguir o perfilar a personas.",
            ),
        ],
        "footnote": (
            "Puedes retirarte cuando quieras: elimina las mallas de la fuente y después la fuente, "
            "y el puente se detiene. Dudas o solicitudes sobre datos: info@sensical.es."
        ),
        "retention_limited": (
            "Esta aceptación es válida durante {days} días. Te avisaremos por correo antes de que "
            "caduque para que puedas renovarla. Si no lo haces, la fuente se pausa y los datos de "
            "sus mallas, incluido cualquier archivo, se borran {grace} días después salvo que "
            "renueves antes."
        ),
        "retention_unlimited": (
            "Los datos de esta fuente se conservan mientras la fuente esté en uso. Cuando una malla "
            "se elimina o deja la fuente, sus datos, incluido cualquier archivo, se borran {grace} "
            "días después."
        ),
    },
}

_COPY = {TermsKind.ACCOUNT: _ACCOUNT, TermsKind.MESH: _MESH, TermsKind.SOURCE: _SOURCE}

def dpa_url() -> str:
    """The Data Processing Agreement the mesh, source and sink terms are accepted under."""
    return f"{settings.PUBLIC_FRONTEND_URL.rstrip('/')}/dpa"


def terms(kind: str, locale: str | None = None) -> dict:
    """The current terms of `kind` in `locale`, falling back to English.

    Mesh and source terms end with how long data is kept; the account terms store none.
    """
    locale = locale if locale in LOCALES else DEFAULT_LOCALE
    text = _COPY[kind][locale]
    footnote = text["footnote"]
    if kind != TermsKind.ACCOUNT:
        grace = settings.DATA_DELETION_GRACE_DAYS
        if settings.DATA_RETENTION_DAYS:
            retention = text["retention_limited"].format(days=settings.DATA_RETENTION_DAYS, grace=grace)
        else:
            retention = text["retention_unlimited"].format(grace=grace)
        footnote = f"{footnote} {retention}"
    return {
        "version": VERSIONS[kind],
        "locale": locale,
        "title": text["title"],
        "description": text["description"],
        "statements": [{"id": sid, "text": body.format(dpa_url=dpa_url())} for sid, body in text["statements"]],
        "footnote": footnote,
    }


def text_hash(served: dict) -> str:
    """sha256 of the terms exactly as served, including the retention sentence."""
    return hashlib.sha256(json.dumps(served, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def is_current(acceptance, kind: str) -> bool:
    """Whether an acceptance is of the current version of `kind` and has not lapsed."""
    return (
        acceptance is not None
        and acceptance.terms_version == VERSIONS[kind]
        and (acceptance.expires_at is None or acceptance.expires_at > timezone.now())
    )


def terms_enforced() -> bool:
    """Whether this instance asks for terms at all. Off on a self-hosted instance."""
    return settings.TERMS_ENFORCED
