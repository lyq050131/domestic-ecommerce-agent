# -*- coding: utf-8 -*-
import os
import sys

# 测试环境固定：不启动定时任务、不推钉钉、不加载向量模型（加速 + CI 可离线）
os.environ.setdefault("AUTO_REPORT_ENABLED", "false")
os.environ.setdefault("DINGTALK_ENABLED", "false")
os.environ.setdefault("EMBEDDING_ENABLED", "false")
os.environ.setdefault("WEB_ACCESS_TOKEN", "")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
