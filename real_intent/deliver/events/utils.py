""" Synchronous implementation of tools for the anthropic API. """
from typing import Literal, Optional, TypedDict, Any
from anthropic.types.beta import (
    BetaToolComputerUse20241022Param,
    BetaToolResultBlockParam, 
    BetaTextBlockParam, 
    BetaImageBlockParam
)
from scrapybara.client import Instance
from scrapybara.anthropic.base import ToolResult, ToolError, CLIResult, BaseAnthropicTool
from playwright.sync_api import sync_playwright
import base64


class BaseTool(BaseAnthropicTool):
    """Base class for all tools that implements common functionality."""

    def __call__(self, **kwargs: Any) -> None:
        pass


class ComputerToolOptions(TypedDict):
    display_height_px: int
    display_width_px: int
    display_number: Optional[int]


class ToolCollection:
    def __init__(self, *tools):
        self.tools = tools
        self.tool_map = {tool.to_params()["name"]: tool for tool in tools}

    def set_instance(self, instance: Instance):
        self.instance = instance

    def to_params(self) -> list:
        return [tool.to_params() for tool in self.tools]

    def run(self, *, name: str, tool_input: dict) -> Optional[ToolResult]:
        tool = self.tool_map.get(name)
        if not tool:
            return None
        try:
            if not self.instance:
                raise ValueError("Instance not set!")
            return tool.call(tool_input, self.instance)
        except Exception as e:
            print(f"Error running tool {name}: {e}")
            return None


class ComputerTool(BaseTool):
    """A computer interaction tool that allows the agent to control mouse and keyboard."""

    api_type: Literal["computer_20241022"] = "computer_20241022"
    name: Literal["computer"] = "computer"
    width: int = 1024
    height: int = 768
    display_num: Optional[int] = 1

    def __init__(self):
        super().__init__()

    @property
    def options(self) -> ComputerToolOptions:
        return {
            "display_width_px": self.width,
            "display_height_px": self.height,
            "display_number": self.display_num,
        }

    def to_params(self) -> BetaToolComputerUse20241022Param:
        return {
            "name": self.name,
            "type": self.api_type,
            "display_width_px": self.width,
            "display_height_px": self.height,
            "display_number": self.display_num,
        }

    def call(self, kwargs: dict, instance: Instance) -> ToolResult:
        action = kwargs.pop("action")
        coordinate = kwargs.pop("coordinate", None)
        text = kwargs.pop("text", None)

        try:
            result = instance.computer(
                action=action,
                coordinate=tuple(coordinate) if coordinate else None,
                text=text,
            )
            return CLIResult(
                output=result.get("output") if result else "",
                error=result.get("error") if result else None,
                base64_image=result.get("base64_image") if result else None,
                system=result.get("system") if result else None,
            )
        except Exception as e:
            raise ToolError(str(e)) from None


def _make_api_tool_result(result: ToolResult, tool_use_id: str) -> BetaToolResultBlockParam:
    tool_result_content: list[BetaTextBlockParam | BetaImageBlockParam] | str = []
    is_error = False
    if result.error:
        is_error = True
        tool_result_content = result.error
    else:
        if result.output:
            tool_result_content.append({
                "type": "text",
                "text": result.output,
            })
        if result.base64_image:
            tool_result_content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": result.base64_image,
                },
            })
    return {
        "type": "tool_result",
        "content": tool_result_content,
        "tool_use_id": tool_use_id,
        "is_error": is_error,
    }


class SearchTool(BaseTool):
    """ Custom tool used to search for a query on Google. Needed to create this as Claude won't correctly target and search for queries. """

    api_type: Literal["custom"] = "custom"
    name: Literal["search"] = "search"
    
    def __init__(self):
        super().__init__()

    def to_params(self) -> dict:
        return {
            "name": self.name,
            "type": self.api_type,
            "input_schema":{
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to enter in the Google's search bar.",
                    },
                },
                "required": ["query"],
            }
        }

    def call(self, kwargs: dict, instance: Instance) -> Any:
        query = kwargs.get("query")
        
        if not query:
            return {"error": "Query parameter is required."}

        return self.perform_search(query, instance)

    def perform_search(self, query: str, instance: Instance) -> ToolResult:
        try:
            url = f"https://www.google.com/search?q={query}"
            cdp_url = instance.browser.start().cdp_url
            with sync_playwright() as playwright:
                browser = playwright.chromium.connect_over_cdp(cdp_url)
                page = browser.new_page()
                page.goto(url)
                page.wait_for_load_state("load")    
                result = {"output": f"Successfully searched for {query}."}
                ss = page.screenshot(full_page=True)      # important, this screenshot is the only way Claude can see the results, the page closes instantly
                result['base64_image'] = base64.b64encode(ss).decode("utf-8")

            return CLIResult(
                output=result.get("output") if result else "",
                error=result.get("error") if result else None,
                base64_image=result.get("base64_image") if result else None,
                system=result.get("system") if result else None,
            )
        except Exception as e:
            raise ToolError(str(e)) from None

