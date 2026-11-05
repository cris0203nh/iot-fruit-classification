"""Adaptador independiente de segmentacion superficial para tomate AGROP-41."""

from PIL import Image

from .surface_analysis import propose_surface_regions
from .surface_masks import describe_surface_masks


PRODUCT = "tomate"

METHOD = "tomato-neutral-background-chroma-proposal-v0.1"

WARNING = (
    "Propuesta cromatica experimental para tomate sobre fondo aproximadamente "
    "neutro. Requiere confirmacion humana. No detecta defectos, madurez "
    "ni conformidad comercial."
)

MASK_WARNING = (
    "Mascara cromatica provisional de tomate. Puede omitir zonas de baja "
    "saturacion o incluir reflejos y artefactos. No equivale a una "
    "segmentacion validada ni a deteccion de defectos."
)


def analyze_tomato_surface(
    image: Image.Image,
    selection=None,
) -> dict:
    """Propone regiones y describe mascaras sin confirmar identidad del tomate."""

    if not isinstance(image, Image.Image):
        raise TypeError("Se requiere una imagen PIL.")

    proposal = propose_surface_regions(image)

    candidates = []

    for candidate in proposal.get("candidates", []):
        adapted = dict(candidate)

        # Eliminar metadato heredado del pipeline de mango.
        adapted.pop("verified_as_mango", None)

        adapted["tomato_identity_confirmed_by_operator"] = False

        candidates.append(adapted)

    proposal = dict(proposal)

    proposal["product"] = PRODUCT
    proposal["method"] = METHOD
    proposal["source_method"] = "neutral-background-chroma-proposal-v0.1"
    proposal["candidates"] = candidates
    proposal["warning"] = WARNING
    proposal["requires_manual_confirmation"] = True

    masks = describe_surface_masks(
        image,
        proposal,
        selection,
    )

    masks = dict(masks)

    masks["product"] = PRODUCT
    masks["warning"] = MASK_WARNING
    masks["requires_independent_validation"] = True

    return {
        "product": PRODUCT,
        "surface_analysis": proposal,
        "mask_analysis": masks,
        "identity_confirmed": False,
        "human_review_required": True,
    }
