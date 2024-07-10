# name: fay_agent.py
# description: Agentic RAG for nl2SQL, 目前的完全体
# author: acxgdxy,Appletree24
# time: 2024/07/03
# 请不要用GPT生成代码中的注释，谢谢。

# 飞书内部文档链接，有对此文件部分代码的解释：https://cqqsgt4nbl1.feishu.cn/wiki/Hr3ewZlTOikzqxkFZWHcPflEnxb?from=from_copylink

# TODO 研究院提供更加优异的文档

import os

from langchain_core.messages import HumanMessage, AIMessage

from tools.MyTimer import MyTimer
from tools.Weather import Weather
from tools.QueryTime import QueryTime
from tools.PythonExecutor import PythonExecutor
from tools.WebPageRetriever import WebPageRetriever
from tools.WebPageScraper import WebPageScraper
from data.province import ProvinceData
from data.city import CityData
from core import content_db

from langchain.agents import AgentExecutor, create_react_agent, Tool
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_qdrant import Qdrant
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_openai import ChatOpenAI
from langchain import PromptTemplate, FewShotPromptTemplate
from langchain_community.utilities import SQLDatabase
from langchain_community.callbacks import get_openai_callback
import src.utils.config_util as utils

from qdrant_client import QdrantClient
from langchain_qdrant import Qdrant

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class FayAgentCore():
    qdrant_retriever: VectorStoreRetriever

    def __init__(self):
        embedding_name = "BAAI/bge-m3"
        embeddings = HuggingFaceEmbeddings(model_name=embedding_name)
        qdrant_client = QdrantClient(location="192.168.100.111:6333")
        qdrant = Qdrant(
            qdrant_client, collection_name="csv_sql_dim_1024", embeddings=embeddings)
        self.qdrant_retriever = qdrant.as_retriever(search_kwargs={"k": 3})
        utils.load_config()
        if str(utils.tavily_api_key) != '':
            os.environ["TAVILY_API_KEY"] = utils.tavily_api_key
        os.environ["OPENAI_API_KEY"] = utils.key_gpt_api_key
        os.environ["OPENAI_API_BASE"] = utils.gpt_base_url
        # 创建llm
        self.llm = ChatOpenAI(model=utils.gpt_model_engine)
        # 保存基本信息到记忆
        utils.load_config()
        # 内存保存聊天历史
        self.chat_history = []
        self.chat_history = []
        if int(utils.max_history_num) > 0:
            old_history = content_db.new_instance().get_list(
                'all', 'desc', int(utils.max_history_num))
            i = len(old_history) - 1
            if len(old_history) > 1:
                while i >= 0:
                    if old_history[i][0] == "member":
                        self.chat_history.append(
                            HumanMessage(content=old_history[i][2]))
                    else:
                        self.chat_history.append(
                            AIMessage(content=old_history[i][2]))
                    i -= 1
            else:
                self.chat_history = []

        """
            请使用本地仓库，原因如下链接 https://cqqsgt4nbl1.feishu.cn/wiki/GtVwwSeXZijfZwkkgCSc7kuqnj6#IcZfdyh2Sol0x0xNivlcI5DAn5b
        """
        # AppleTree24 本地仓库
        db_user = "root"
        db_password = "AI20240520"
        db_host = "192.168.100.111"
        db_name = "ai_use"

        # from urllib.parse import quote_plus
        # 阿里云仓库
        # db_user = "xxx"
        # db_password = quote_plus("xxxx")
        # db_host = "xxx"
        # db_name = "xxx"

        db_uri = f"mysql+pymysql://{db_user}:{db_password}@{db_host}/{db_name}"
        db = SQLDatabase.from_uri(db_uri)
        db._sample_rows_in_table_info = 3  # 将底部的样例输出修改为0
        self.db = db

        # 创建agent chain
        my_timer = MyTimer()
        weather_tool = Weather()
        query_time = QueryTime()
        # query_timer_db_tool = QueryTimerDB()
        # delete_timer_tool = DeleteTimer()
        python_executor = PythonExecutor()
        web_page_retriever = WebPageRetriever()
        web_page_scraper = WebPageScraper()
        # list_sql = ListSql()
        # toolkit = MySQLDatabaseToolkit(db=db, llm=self.llm)
        # tools = toolkit.get_tools()

        # 输入数据处理
        self.province_data = ProvinceData()
        self.city_data = CityData()
        toolkit = SQLDatabaseToolkit(db=self.db, llm=self.llm)
        self.tools = toolkit.get_tools()
        if str(utils.tavily_api_key) != '':
            self.tools.append(TavilySearchResults(max_results=1))

        with open(os.path.join(BASE_DIR, 'template.txt'), "r", encoding='utf-8') as f:
            template = f.read()
            prompt = PromptTemplate(
                input_variables=[
                    'agent_scratchpad',
                    'chat_history',
                    'input',
                    'tools',
                    'tool_names'
                ],
                template=template,
            )

            agent = create_react_agent(self.llm, self.tools, prompt)
            # 通过传入agent和tools来创建一个agent executor
            self.agent = AgentExecutor(
                agent=agent,
                tools=self.tools,
                verbose=True,
                handle_parsing_errors=True,
                max_iterations=10,
                max_execution_time=60,
                trim_intermediate_steps=3
            )
            self.total_tokens = 0
            self.total_cost = 0

    # 记忆prompt
    def set_history(self, result):

        if (len(self.chat_history) >= int(utils.max_history_num)):
            del self.chat_history[0]
            del self.chat_history[0]
        if result:
            if isinstance(result, dict):
                self.chat_history.append(HumanMessage(content=result['input']))
                self.chat_history.append(AIMessage(content=result['output']))

    def run(self, input_text, retriever: VectorStoreRetriever):
        result = ""
        re = ""
        try:
            input_text = input_text.replace(
                '主人语音说了：', '').replace('主人文字说了：', '')
            RAG_ENHANCE_PROMPT = str(retriever.invoke(input_text))
            input_text = input_text+RAG_ENHANCE_PROMPT
            with get_openai_callback() as cb:
                # result = self.agent.run(agent_prompt)
                result = self.agent.invoke(
                    {"input": input_text, "chat_history": self.chat_history})
                re = "执行完毕" if re is None or re == "N/A" else result['output']
                self.total_tokens = self.total_tokens + cb.total_tokens

        except Exception as e:
            print(e)

        chat_text = re

        # 保存聊天对话
        if int(utils.max_history_num) > 0:
            self.set_history(result)

        return False, chat_text


if __name__ == "__main__":
    agent = FayAgentCore()
    while True:
        user_input = input("User: ")
        if user_input.lower() in ["quit", "exit", "q"]:
            print("再见!")
            break
        agent.run(user_input, retriever=agent.qdrant_retriever)
