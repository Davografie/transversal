"""Image metadata for viewer surfaces — the resolved image *plus* its provenance.

Split into its own module because both `entities.py` and `traits.py` need it, and
`entities.py` already imports `traits.py` — so neither can host it without a
cycle.
"""

from typing import Optional

import strawberry

from transversal.domain import MediaImage


@strawberry.type
class CreditRef:
    """One credited party on an image — TASL's *Author* or *Source*."""
    role: str
    name: str = ""
    url: str = ""


@strawberry.type
class ImageInfo:
    """A resolved image, and what a viewer should say about it.

    ``image(role)`` returns only a URL. A viewer that wants to show provenance —
    the AI labels, who made the artwork, where it came from online — needs the
    record's metadata alongside the URL, which is what this carries. Read-only
    surfaces (the sheet's portrait viewer, a trait row) use it; authoring happens
    over REST.
    """
    url: str
    role: str = ""
    transparent: bool = False
    flags: list[str] = strawberry.field(default_factory=list)
    credits: list[CreditRef] = strawberry.field(default_factory=list)
    license: str = ""
    credit_text: str = ""


def build_image_info(img: MediaImage, role: str, url: str) -> ImageInfo:
    """Assemble the GraphQL view of a resolved image record."""
    return ImageInfo(
        url=url,
        role=role,
        transparent=bool(img.transparent),
        flags=list(img.flags),
        credits=[CreditRef(role=c.role, name=c.name, url=c.url) for c in img.credits],
        license=img.license,
        credit_text=img.credit_text,
    )
