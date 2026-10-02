"""The terms owners accept: account terms at signup, mesh terms per default-broker mesh,
source terms per source and sink terms per sink.

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
    TermsKind.SINK: "sinks-2026-10",
}

# The console mock (apps/api-mock/src/features/terms/terms.ts) carries a copy of this text
# and must be kept in sync.
_ACCOUNT = {
    "en": {
        "title": "Before you create your account",
        "description": (
            "Your account lets you sign in, explore public meshes and manage your profile. It "
            "stores only your name, email address and settings. Creating a mesh, which stores data "
            "from its devices, will ask you to accept its own terms at that point."
        ),
        "statements": [
            ("terms", "I accept the Mesh Things Terms of Use."),
            ("privacy", "I've read the Privacy Policy, which explains how my name and email address are used."),
        ],
        "footnote": (
            "You can delete your account at any time from your profile. For questions or data requests please email us at: "
            "info@sensical.es."
        ),
    },
    "es": {
        "title": "Antes de crear tu cuenta",
        "description": (
            "Tu cuenta te permite iniciar sesión, explorar mallas públicas y gestionar tu perfil. Solo "
            "guardamos tu nombre, tu correo y tus ajustes. Cuando crees una malla, guardaremos los datos de sus "
            "dispositivos. Te pediremos aceptar sus propias condiciones en ese momento."
        ),
        "statements": [
            ("terms", "Acepto las Condiciones de uso de Mesh Things."),
            ("privacy", "He leído la Política de privacidad, que explica cómo se usan mi nombre y mi correo."),
        ],
        "footnote": (
            "Puedes eliminar tu cuenta cuando quieras desde tu perfil. Puedes escribirnos con dudas o solicitudes sobre datos a través de: "
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
                "Agreement. "
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
            "You can withdraw at any time by deleting the mesh. For questions or data requests please email us at: "
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
            "Una malla guarda el tráfico que sus gateways envían al broker por defecto. Ese tráfico "
            "puede incluir datos personales de personas que nunca se han registrado aquí: nombres de "
            "nodo, identificadores de dispositivo, posiciones y telemetría. En esta malla tú "
            "decides qué se recoge y para qué, y Sensical lo trata solo por tu cuenta para prestar el "
            "servicio. Marca cada casilla para continuar."
        ),
        "statements": [
            (
                "controller",
                "Actúo como responsable del tratamiento del tráfico que trae esta malla. Autorizo a "
                "Sensical a recibirlo, descifrarlo y almacenarlo en mi cuenta como encargado del "
                "tratamiento, según el Acuerdo de procesamiento de los datos. Si soy 'operador', esto incluye "
                "conservar los dispositivos que elija en un archivo a largo plazo que puedo descargar.",
            ),
            (
                "lawfulBasis",
                "Tengo una base legal para este tratamiento, como un interés legítimo, e informo a las "
                "personas cuyos nodos aparecen en esta malla de cómo se usan sus datos.",
            ),
            (
                "minimisation",
                "Guardaré solo lo que esta malla necesite: registraré solo sus propias pasarelas y, si "
                "guardo datos de dispositivos a largo plazo, solo los que necesite y solo mientras los necesite.",
            ),
            (
                "sensitive",
                "No usaré esta malla para recoger datos sensibles, como información de salud, ni para "
                "seguir o perfilar a personas.",
            ),
        ],
        "footnote": (
            "Puedes retirarte cuando quieras eliminando la malla. Puedes escribirnos con dudas o solicitudes sobre datos a través de: "
            "info@sensical.es."
        ),
        "retention_limited": (
            "La aceptación de estas condiciones es válida durante {days} días. Te avisaremos por correo antes de que "
            "caduque para que puedas renovarla. Si no lo haces, la malla dejará de guardar datos nuevos, "
            "y los datos guardados, incluido cualquier archivo, se borrarán {grace} días después salvo "
            "que renueves estas condiciones antes."
        ),
        "retention_unlimited": (
            "Los datos de la malla se conservan mientras la malla esté en uso. Cuando la eliminas, sus "
            "datos, incluido cualquier archivo guardado, se borran {grace} días después."
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
                "Data Processing Agreement. This includes keeping the devices I choose in a long-term archive "
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
            "bridge stops. For questions or data requests, email us at: info@sensical.es."
        ),
        "retention_limited": (
            "This acceptance is valid for {days} days. We'll email you before it lapses so you can "
            "renew it. If you don't, the source will be paused, and the data of its meshes, including "
            "any archive, will be deleted {grace} days later unless you renew before the expiration."
        ),
        "retention_unlimited": (
            "Data from this source is kept while the source is in use. If a mesh is deleted or "
            "moved off the source, its data, including any archive, will be deleted {grace} days later."
        ),
    },
    "es": {
        "title": "Antes de conectar una fuente",
        "description": (
            "Una fuente trae a Mesh Things el tráfico de un broker que tú eliges. Ese tráfico puede "
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
                "tratamiento, según el Acuerdo de procesamiento de los datos. Esto incluye conservar los "
                "dispositivos que elija en un archivo a largo plazo que puedo descargar.",
            ),
            (
                "authority",
                "Estoy autorizado a usar este broker, sus credenciales y la clave de cifrado de la "
                "malla, y traer este tráfico no incumple las normas del broker ni del canal.",
            ),
            (
                "lawfulBasis",
                "Tengo una base legal para este tratamiento, como un interés legítimo, e informo a "
                "las personas cuyos nodos aparecen en este canal de cómo se usan sus datos.",
            ),
            (
                "minimisation",
                "Usaré el filtro de 'tópico` más restringido que cubra mi malla, no traeré tráfico que no "
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
            "y el puente se detiene. Para dudas o solicitudes sobre datos, escríbenos en: info@sensical.es."
        ),
        "retention_limited": (
            "La aceptación de estos términos es válida durante {days} días. Te avisaremos por correo antes de que "
            "caduque para que puedas renovarla. Si no lo haces, la fuente se pausará y los datos de "
            "sus mallas, incluido cualquier archivo, se borrarán {grace} días después salvo que "
            "los renueves antes."
        ),
        "retention_unlimited": (
            "Los datos de esta fuente se conservan mientras la fuente esté en uso. Cuando una malla "
            "se elimina o deja la fuente, sus datos, incluido cualquier archivo, se borran {grace} "
            "días después."
        ),
    },
}

# The operator is the controller of the readings a sink sends to a third party.
_SINK = {
    "en": {
        "title": "Before you create a sink",
        "description": (
            "A sink lets a service you choose subscribe to readings from your meshes and devices, "
            "with credentials you, and only you, hold. Those readings can include personal data from people "
            "who never signed up here: node names, device IDs, positions and telemetry. You decide "
            "who receives them and why, and Sensical sends them only on your instructions. Tick each "
            "box to continue."
        ),
        "statements": [
            (
                "controller",
                "I act as data controller for the readings this sink sends. I instruct Sensical, as "
                "processor under the Data Processing Agreement, to make them available to "
                "whoever holds the sink's credentials.",
            ),
            (
                "recipient",
                "I'll give the credentials only to recipients I trust with this data, and I'm "
                "responsible for how they use it.",
            ),
            (
                "lawfulBasis",
                "I have a lawful basis for sharing these readings, and I tell the people whose nodes "
                "appear in them who receives their data.",
            ),
            (
                "minimisation",
                "I'll attach only the meshes and devices the recipient needs, choose only the streams "
                "it needs, and remove them when it no longer does.",
            ),
        ],
        "footnote": (
            "You can withdraw at any time: detach the sink's meshes and devices, then delete the "
            "sink, and its credentials stop working. For questions or data requests, email us at: info@sensical.es."
        ),
        "retention_limited": (
            "This acceptance is valid for {days} days. We'll email you before it lapses so you can "
            "renew it. If you don't, the sink will be paused, and it will stop sending data. Its credentials "
            "are refused until you renew. A sink keeps no data of its own."
        ),
        "retention_unlimited": (
            "A sink keeps no data of its own. It sends readings while it is in use and stops when you "
            "delete it."
        ),
    },
    "es": {
        "title": "Antes de crear un destino",
        "description": (
            "Un destino permite que un servicio que tú eliges se suscriba a las lecturas de tus "
            "mallas y dispositivos, con credenciales que solo tú tienes. Esas lecturas pueden incluir "
            "datos personales de personas que nunca se han registrado aquí: nombres de nodo, "
            "identificadores de dispositivo, posiciones y telemetría. Tú decides quién las recibe y "
            "para qué, y Sensical las envía solo siguiendo tus instrucciones. Marca cada casilla para "
            "continuar."
        ),
        "statements": [
            (
                "controller",
                "Actúo como responsable del tratamiento de las lecturas que envía este destino. "
                "Encargo a Sensical, como encargado del tratamiento según el Acuerdo de procesamiento de "
                "los datos, ponerlas a disposición de quien tenga las credenciales del "
                "destino.",
            ),
            (
                "recipient",
                "Daré las credenciales solo a destinatarios de confianza para estos datos, y soy "
                "responsable del uso que hagan de ellos.",
            ),
            (
                "lawfulBasis",
                "Tengo una base legal para compartir estos datos, e informo a las personas cuyos "
                "nodos aparecen en ellas de quién recibe sus datos.",
            ),
            (
                "minimisation",
                "Asociaré solo las mallas y dispositivos que el destinatario necesite, elegiré solo los "
                "flujos que necesite y los quitaré cuando ya no los necesite.",
            ),
        ],
        "footnote": (
            "Puedes retirarte cuando quieras: quita las mallas y dispositivos del destino y después "
            "elimínalo, y sus credenciales dejan de funcionar. Para dudas o solicitudes sobre datos, puedes escribirnos en: "
            "info@sensical.es."
        ),
        "retention_limited": (
            "La aceptación de estos términos es válida durante {days} días. Te avisaremos por correo antes de que "
            "caduque para que puedas renovarla. Si no lo haces, el destino se pausará: no se enviará nada "
            "más y sus credenciales se rechazarán hasta que renueves esta aceptación. Un destino no guarda datos propios."
        ),
        "retention_unlimited": (
            "Un destino no guarda datos propios. Envía lecturas mientras está en uso y deja de hacerlo "
            "cuando lo eliminas."
        ),
    },
}

_COPY = {TermsKind.ACCOUNT: _ACCOUNT, TermsKind.MESH: _MESH, TermsKind.SOURCE: _SOURCE, TermsKind.SINK: _SINK}


def dpa_url() -> str:
    """The Data Processing Agreement the mesh, source and sink terms are accepted under."""
    return f"{settings.PUBLIC_FRONTEND_URL.rstrip('/')}/dpa"


def dpa_url() -> str:
    """The Data Processing Agreement the mesh, source and sink terms are accepted under."""
    return f"{settings.PUBLIC_FRONTEND_URL.rstrip('/')}/dpa"


def terms(kind: str, locale: str | None = None) -> dict:
    """The current terms of `kind` in `locale`, falling back to English.

    Mesh, source and sink terms end with how long data is kept, or for a sink how long the
    acceptance lasts; the account terms store none.
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
