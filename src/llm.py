from contextlib import nullcontext
from typing import Any, List, Literal, Optional

from langchain.output_parsers import PydanticOutputParser
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from .prompts import VEHICLE_EXPORT_EXTRA, VEHICLE_EXPORT_SYSTEM, VEHICLE_EXPORT_USER


class Item(BaseModel):
    name: str = Field(
        description="Full english vehicle name, including type (T72M1 MBT, M113 APC etc), with any quotes properly escaped."
    )
    ownership: Optional[Literal["ru", "ua"]] = Field(
        description="Who equipment belonged to originally (required, unless neither is specified)"
    )
    status: Literal["damaged", "destroyed", "captured"] = Field(
        description="Status of the equipment (damaged if it was left behind)"
    )
    post_date: Optional[str] = Field(
        description="If provided, the format is day.month.year (e.g. 20.4.2024) or season name with year, defaulting to the first date of certain month (rules: winter -> 01.01, spring -> 01.03, summer -> 01.06, fall -> 01.09). If only the year was provided, assume first date of december."
    )


class Vehicles(BaseModel):
    vehicles: List[Item] = Field(description="List of vehicle objects that were detected")


async def parse_messages(texts: list[str], extra_prompt: str, sem=Optional[Any]) -> list[Item]:
    async with sem or nullcontext():
        parser = PydanticOutputParser(pydantic_object=Vehicles)
        fmt = parser.get_format_instructions()
        system_extra = VEHICLE_EXPORT_EXTRA.format(fmt=fmt, extra=extra_prompt)
        user_message = VEHICLE_EXPORT_USER.format("\n\n".join([f"<message>\n{t}\n</message>" for t in texts]))
        messages = [{"role": "system", "content": VEHICLE_EXPORT_SYSTEM + system_extra}, user_message]
        result_raw = await ChatOpenAI(model="o3-mini").ainvoke(messages)
        return parser.parse(result_raw.content).vehicles
