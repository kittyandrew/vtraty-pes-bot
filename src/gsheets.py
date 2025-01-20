import itertools
from enum import Enum

import aiohttp


class CustomEnum(Enum):
    # Source: https://stackoverflow.com/a/71839532
    def __lt__(self, other: "CustomEnum"):
        return self.value < other.value

    def __gt__(self, other: "CustomEnum"):
        return not (self < other)

    def __ge__(self, other: "CustomEnum"):
        if self == other:
            return True
        return not (self < other)


async def get_gsheet_prompt(spreadsheet_id, api_key):
    sheet_name = "table"
    # Construct the URL for the Google Sheets API
    base_url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{sheet_name}"

    async def _get_list_prompt(rang: str):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{base_url}!{rang}?alt=json&key={api_key}") as resp:
                data = await resp.json()
                return "\n".join(f"{l.strip()} - {r.strip()}" for l, r in data["values"])

    text = "\nCommon keywords:\n"
    text += await _get_list_prompt("D2:E")
    text += "\nNon-exhaustive list of common vehicles for reference:\n"
    text += await _get_list_prompt("A2:B")
    return text


async def get_vehicle_types(spreadsheet_id, api_key):
    sheet_name = "table"
    # Construct the URL for the Google Sheets API
    base_url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{sheet_name}"

    async def _get(rang: str):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{base_url}!{rang}?alt=json&key={api_key}") as resp:
                data = await resp.json()
                return list(l.strip() for l in itertools.chain(*data["values"]))

    type_strings = await _get("C2:C")
    if any(s.lower() == "unknown" for s in type_strings):
        return CustomEnum("VehicleTypes", type_strings)
    return CustomEnum("VehicleTypes", type_strings + ["UNKNOWN"])
