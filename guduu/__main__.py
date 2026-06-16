"""CosMac Star 主 AI Bot 的启动入口。

用法（在项目根目录、且已激活/指定 .venv）：
    python -m guduu

环境变量可覆盖配置，例如换模型后端：
    GUDUU_LLM_PROVIDER=echo python -m guduu
"""

from __future__ import annotations

import logging

from guduu.bots.appservice_bot import run
from guduu.config import GuduuConfig


def main() -> None:
    # 统一日志格式，方便观察主 AI"看到了什么、做了什么"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    config = GuduuConfig.from_env()
    run(config)


if __name__ == "__main__":
    main()
