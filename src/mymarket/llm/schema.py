"""Bounded explanation schema and grounding checks."""

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProductImpact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product: str
    direction: Literal["UP", "DOWN", "STABLE"]
    why: str = Field(min_length=1, max_length=400)


class Explanation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    headline: str = Field(min_length=1, max_length=160)
    domain_impact: str = Field(min_length=1, max_length=600)
    product_impacts: list[ProductImpact] = Field(min_length=1, max_length=4)
    confidence_note: str = Field(min_length=1, max_length=400)
    disclaimer: str = Field(min_length=1, max_length=160)

    @field_validator("headline")
    @classmethod
    def short_headline(cls, value):
        if len(value.split()) > 12:
            raise ValueError("Headline must be at most twelve words")
        return value


# A deliberately small general vocabulary. Unknown factual words and names cause
# a template fallback rather than accepting ungrounded provider text.
GRAMMAR = set("""a an the this that these those and or but with without for from to of in on at
is are was were be been being may might could can will not no only awareness financial advice
price prices pricing supply costs cost pressure news article reports suggests suggests higher lower
rise rising increase increasing up down stable unchanged shoppers product products impact expected
prediction model confidence uncertain uncertainty evidence limited low high current change changes
based given provided facts source data future forecast result results do does should remain remains
because due reflects possible possibility direction probability probabilities trend latest information
rice egg eggs cooking oil chicken staple food demand subsidy shortage flood feed risk risks
theft availability imports exports import export tariff tariffs levy control policy government
harga mungkin boleh naik turun kekal stabil tidak berubah untuk pengguna pembeli bekalan kos berita
artikel laporan menunjukkan tekanan berdasarkan maklumat diberi data semasa keyakinan rendah tinggi
ramalan model terhad ketidakpastian sahaja kesedaran bukan nasihat kewangan dan atau dengan tanpa
ini itu adalah pada dalam daripada kepada kerana akibat kemungkinan beras telur minyak masak ayam
subsidi kekurangan banjir kawalan dasar kadar hasil produk makanan harian dijangka perubahan
""".split())


def validate_grounding(explanation: Explanation, facts: dict, lang: str):
    prediction = facts["prediction"]
    if len(explanation.product_impacts) != 1:
        raise ValueError("Expected one product impact")
    impact = explanation.product_impacts[0]
    if impact.product != prediction["product"] or impact.direction != prediction["direction"]:
        raise ValueError("Explanation changes computed prediction")
    text = " ".join([explanation.headline, explanation.domain_impact, impact.why, explanation.confidence_note, explanation.disclaimer])
    given = json.dumps(facts, ensure_ascii=False)
    figures = json.dumps({"prediction": prediction, "price_context": facts["price_context"]}, ensure_ascii=False)
    # Publication dates and URL digits cannot justify a price or probability figure.
    figures = re.sub(r'"data_as_of"\s*:\s*"[^"]*"', '', figures)
    if set(re.findall(r"-?\d+(?:\.\d+)?", text)) - set(re.findall(r"-?\d+(?:\.\d+)?", figures)):
        raise ValueError("Explanation introduces a new figure")
    allowed = set(re.findall(r"\w+", given.casefold())) | GRAMMAR
    if set(re.findall(r"\w+", text.casefold())) - allowed:
        raise ValueError("Explanation introduces unsupported factual words or names")
    expected = "Kesedaran sahaja, bukan nasihat kewangan." if lang == "ms" else "Awareness only, not financial advice."
    if explanation.disclaimer != expected:
        raise ValueError("Disclaimer differs from required text")
