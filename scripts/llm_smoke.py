# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agents.base_agent import BaseAgent
a = BaseAgent("连通性测试")
text = a.call_llm("请只回复四个字：一切正常", "你是测试助手")
print("DeepSeek reply:", text.strip()[:80])