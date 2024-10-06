from typing import List, Literal, Optional

from langchain.output_parsers import PydanticOutputParser
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from .prompts import VEHICLE_EXPORT_SYSTEM, VEHICLE_EXPORT_USER


class Item(BaseModel):
    name: str = Field(description="Full english vehicle name, including type (T72M1 MBT, M113 APC etc)")
    ownership: Literal["ru", "ua"] = Field(description="Who equipment belonged to originally")
    status: Literal["damaged", "destroyed", "captured"] = Field(
        description="Status of the equipment (damaged if it was left behind)"
    )
    post_date: Optional[str] = Field(
        description="If provided, the format is day.month.year (e.g. 20.4.2024) or season name with year, in which case you should default to middle month and first date of that season (e.g. summer 2024 -> 1.7.2024)"
    )


class Vehicles(BaseModel):
    vehicles: List[Item] = Field(description="List of vehicle objects that were detected")


async def parse_messages(texts: list[str], extra_prompt: str) -> list[Item]:
    parser = PydanticOutputParser(pydantic_object=Vehicles)
    fmt = parser.get_format_instructions()
    system_message = VEHICLE_EXPORT_SYSTEM.format(fmt=fmt, extra=extra_prompt)
    user_message = VEHICLE_EXPORT_USER.format("\n\n".join([f"<message>\n{t}\n</message>" for t in texts]))
    messages = [{"role": "system", "content": system_message}, user_message]
    result_raw = await ChatOpenAI(temperature=0, model_name="gpt-4o").ainvoke(messages)
    return parser.parse(result_raw.content).vehicles
