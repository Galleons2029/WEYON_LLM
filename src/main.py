"""
启动入口
"""
from langchain_core.runnables import Runnable
from starlette.staticfiles import StaticFiles

import logs
from agent.fay_agent import FayAgentCore
from basic import default_context
from chains import simple_chain, profile_query

_ = simple_chain, profile_query


def history_chat_build(history):
    # 历史对话总是从用户开始，然后机器人
    history_msg = []
    history = history[-default_context['remember_history']:]
    for i, (user_message, bot_message) in enumerate(history):
        if isinstance(user_message, list):
            user_message = "".join(user_message)
        history_msg.append(('user', user_message))
        if isinstance(bot_message, list):
            bot_message = "".join(bot_message)
        history_msg.append(('ai', bot_message))
    history_msg = str(history_msg).replace(r"\n", "\n")
    return history_msg


def profile_rag_msg(message, history):
    history_msg = history_chat_build(history)
    pro_chain: Runnable = default_context['profile_query']
    res = pro_chain.invoke({'chat_history': history_msg, 'question': message})
    partial_message = ""
    if res['keywords']:
        tips = f"> 🤗关键词 : **{res['keywords']}**\n\n"
        partial_message += tips
        yield partial_message
    retriever_chain: Runnable = default_context['retriever_chain']

    for chunk in retriever_chain.stream(res):
        partial_message += chunk.content
        yield partial_message


def profile_rag(message, history):
    chain: Runnable = default_context['profile_query_rag']
    history_msg = history_chat_build(history)
    partial_message = ""
    logs.get_logger('chat').debug(history_msg)
    for chunk in chain.stream({"question": message, "chat_history": history_msg}):
        partial_message = partial_message + chunk.content
        yield partial_message


def simple_rag(message, history):
    chain: Runnable = default_context['simple_chain']
    # 历史对话总是从用户开始，然后机器人
    history_msg = history_chat_build(history)
    partial_message = ""
    logs.get_logger('chat').debug(history_msg)
    for chunk in chain.stream([message, history_msg]):
        partial_message = partial_message + chunk.content
        yield partial_message


def simple_chat(message, history):
    chain: Runnable = default_context['ServeChatModel']
    # 历史对话总是从用户开始，然后机器人
    history_msg = history_chat_build(history)
    partial_message = ""
    logs.get_logger('chat').debug(history_msg)
    for chunk in chain.stream([history_msg, message]):
        partial_message = partial_message + chunk.content
        yield partial_message


agent = FayAgentCore()


def simple_agent(message, history):
    user_input = message
    return agent.run(user_input, agent.qdrant_retriever)[1]


# 公司名称
company_name = "WeYon"
con_limit = 20

import gradio as gr

if __name__ == "__main__":
    rag_interface = gr.ChatInterface(simple_rag, title=f"{company_name} Question Rag", concurrency_limit=con_limit,
                                     description=f"{company_name} 基于问题检索对话")
    profile_interface = gr.ChatInterface(profile_rag_msg, title=f"{company_name} Keywords Rag",
                                         concurrency_limit=con_limit,
                                         description=f"{company_name} 基于关键词检索")
    chat_interface = gr.ChatInterface(simple_chat, title=f"{company_name} Chat", concurrency_limit=con_limit,
                                      description=f"{company_name} 直接与模型对话")
    agent_interface = gr.ChatInterface(simple_agent, title=f"{company_name} Agent", concurrency_limit=con_limit,
                                       description=f"{company_name} 查询数据库的智能体")

    from fastapi import FastAPI

    app = FastAPI()
    gr.mount_gradio_app(app, rag_interface, path="/rag")
    gr.mount_gradio_app(app, profile_interface, path="/profile/")
    gr.mount_gradio_app(app, chat_interface, path="/chat")
    gr.mount_gradio_app(app, agent_interface, path="/agent")

    app.mount("/", StaticFiles(directory="./pages", html=True), name="pages")

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=7860)
