import re
from typing import Union
import threading

from langchain_core.agents import AgentAction, AgentFinish
from langchain_core.exceptions import OutputParserException

from langchain.agents.agent import AgentOutputParser
from langchain.agents.mrkl.prompt import FORMAT_INSTRUCTIONS
from langchain_community.utilities.sql_database import SQLDatabase
from langchain_core.pydantic_v1 import Field

from agent.agents.tools.data_to_markdown import DataTreating

# FINAL_ANSWER_ACTION = "Final Answer:"
# FINAL_SQL = "SQL:"
# MISSING_ACTION_AFTER_THOUGHT_ERROR_MESSAGE = (
#     "Invalid Format: Missing 'Action:' after 'Thought:"
# )
# MISSING_ACTION_INPUT_AFTER_ACTION_ERROR_MESSAGE = (
#     "Invalid Format: Missing 'Action Input:' after 'Action:'"
# )
# FINAL_ANSWER_AND_PARSABLE_ACTION_ERROR_MESSAGE = (
#     "Parsing LLM output produced both a final answer and a parse-able action:"
# )

FINAL_ANSWER_ACTION = "最终答案："
FINAL_SQL = "SQL："
MISSING_ACTION_AFTER_THOUGHT_ERROR_MESSAGE = (
    "无效格式： 在'思考：'之后缺少'行动：'"
)
MISSING_ACTION_INPUT_AFTER_ACTION_ERROR_MESSAGE = (
    "无效格式： 在'行动：'之后缺少'行动输入：'"
)
FINAL_ANSWER_AND_PARSABLE_ACTION_ERROR_MESSAGE = (
    "解析LLM输出生成最终答案和可解析的操作："
)


class ReActSingleInputOutputParser(AgentOutputParser):
    output_form: bool
    db: SQLDatabase = Field(exclude=True)
    """Parses ReAct-style LLM calls that have a single tool input.

    Expects output to be in one of two formats.

    If the output signals that an action should be taken,
    should be in the below format. This will result in an AgentAction
    being returned.

    ```
    Thought: agent thought here
    Action: search
    Action Input: what is the temperature in SF?
    ```

    If the output signals that a final answer should be given,
    should be in the below format. This will result in an AgentFinish
    being returned.

    ```
    Thought: agent thought here
    Final Answer: The temperature is 100 degrees
    ```

    """

    class Config:
        """Configuration for this pydantic object."""

        arbitrary_types_allowed = True

    def get_format_instructions(self) -> str:
        return FORMAT_INSTRUCTIONS

    def parse(self, text: str) -> Union[AgentAction, AgentFinish]:
        includes_answer = FINAL_ANSWER_ACTION in text
        regex = (
            r"行动\s*\d*\s*：[\s]*(.*?)[\s]*行动\s*\d*\s*输入\s*\d*\s*：[\s]*(.*)"
        )
        action_match = re.search(regex, text, re.DOTALL)
        if action_match:
            if includes_answer:
                raise OutputParserException(
                    f"{FINAL_ANSWER_AND_PARSABLE_ACTION_ERROR_MESSAGE} {text}"
                )
            action = action_match.group(1).strip()
            action_input = action_match.group(2)
            tool_input = action_input.strip(" ")
            tool_input = tool_input.strip('"')

            return AgentAction(action, tool_input, text)

        elif includes_answer:
            print("1", self.output_form)
            if self.output_form:
                # 按照行分割文本
                lines = text.splitlines()
                # 找到包含"SQL:"的那一行，并提取其内容
                sql_query_line = next((line for line in lines if "SQL：" in line), None)
                sql = sql_query_line.split(FINAL_SQL)[-1].strip()
                data_treating = DataTreating().data_to_markdown
                # 创建线程来进行数据处理
                thread = threading.Thread(target=data_treating(self.db.run_no_throw(sql)))
                thread.start()

            return AgentFinish(
                {"output": text.split(FINAL_ANSWER_ACTION)[-1].strip()}, text
            )

        print("1", re.search(r"行动\s*\d*\s*：[\s]*(.*?)", text, re.DOTALL))
        print("2", re.search(
            r"[\s]*行动\s*\d*\s*输入\s*\d*\s*：[\s]*(.*)", text, re.DOTALL
        ))
        print("3", text)

        if not re.search(r"行动\s*\d*\s*：[\s]*(.*?)", text, re.DOTALL):
            raise OutputParserException(
                f"Could not parse LLM output: `{text}`",
                observation=MISSING_ACTION_AFTER_THOUGHT_ERROR_MESSAGE,
                llm_output=text,
                send_to_llm=True,
            )
        elif not re.search(
                r"[\s]*行动\s*\d*\s*输入\s*\d*\s*：[\s]*(.*)", text, re.DOTALL
        ):
            raise OutputParserException(
                f"Could not parse LLM output: `{text}`",
                observation=MISSING_ACTION_INPUT_AFTER_ACTION_ERROR_MESSAGE,
                llm_output=text,
                send_to_llm=True,
            )
        else:
            raise OutputParserException(f"Could not parse LLM output: `{text}`")

    @property
    def _type(self) -> str:
        return "react-single-input"
