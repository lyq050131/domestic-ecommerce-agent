"""国内电商店铺自动化运营智能体 v3.1 - 主程序入口（真实店铺运营版）"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import settings
from agents.product_selection_agent import product_selection_agent
from agents.ad_optimization_agent import ad_optimization_agent
from agents.customer_service_agent import customer_service_agent
from retrieval.mobius_loop import mobius_loop
from utils.logger import logger


def print_banner():
    banner = f"""
╔══════════════════════════════════════════════════════════════╗
║  国内电商店铺自动化运营智能体 v3.1（真实店铺运营版）              ║
║  数据源: 真实淘宝客 API                                       ║
║  LLM  : DeepSeek {settings.LLM_MODEL}                        ║
║  选品 Agent | 投放优化 Agent | 多语言客服 Agent             ║
║  自反馈知识闭环：质量门控 → 向量回流 → 越用越准              ║
╚══════════════════════════════════════════════════════════════╝
    """
    print(banner)


def run_product_selection():
    print("\n" + "=" * 60)
    print("📦 模块1：选品Agent - 淘宝商品分析与选品推荐")
    print("=" * 60)
    category = input("\n请输入要分析的品类（如：无线蓝牙耳机）：").strip() or "无线蓝牙耳机"
    print(f"\n🔍 正在抓取淘宝客真实数据并分析品类: {category} ...\n")
    result = product_selection_agent.analyze_category(category)
    print("\n" + "=" * 60)
    print("📊 选品分析报告")
    print("=" * 60)
    print(result["report"])
    print("\n" + "-" * 60)
    print(f"✅ 闭环回流状态: {'成功' if result['feedback_success'] else '未通过质量门控或重复'}")
    return result


def run_ad_optimization():
    print("\n" + "=" * 60)
    print("📈 模块2：投放优化Agent - 淘宝联盟推广优化")
    print("=" * 60)
    top_n = input("\n请输入每个关键词分析的推广商品数（默认15）：").strip()
    top_n = int(top_n) if top_n.isdigit() else 15
    print(f"\n📊 正在抓取淘宝联盟真实推广数据并生成优化方案...\n")
    result = ad_optimization_agent.optimize_campaigns(top_n=top_n)
    print("\n" + "=" * 60)
    print("💡 推广优化方案")
    print("=" * 60)
    print(result["optimization_strategy"])
    print("\n" + "-" * 60)
    print(f"✅ 闭环回流状态: {'成功' if result['feedback_success'] else '未通过质量门控或重复'}")
    return result


def run_customer_service():
    print("\n" + "=" * 60)
    print("💬 模块3：多语言客服Agent - 差评/私信自动回复")
    print("=" * 60)
    review = input("\n请输入评论或私信内容（默认英文差评）：").strip() or "The product stopped working after 3 days. Very disappointed."
    rating_input = input("请输入评分（1-5，私信可回车跳过）：").strip()
    rating = int(rating_input) if rating_input.isdigit() else None
    if rating is not None:
        result = customer_service_agent.handle_review(review, rating)
    else:
        result = customer_service_agent.handle_message(review)
    print("\n" + "=" * 60)
    print("💬 客服回复")
    print("=" * 60)
    print(f"检测语言: {result['detected_language']}")
    if result.get("matched_template"):
        print(f"命中模板: {result['matched_template']}")
    print(f"\n回复内容:\n{result['reply']}")
    print("\n" + "-" * 60)
    print(f"✅ 闭环回流状态: {'成功' if result['feedback_success'] else '未通过质量门控或重复'}")
    return result


def run_loop_stats():
    print("\n" + "=" * 60)
    print("🔄 模块4：自反馈闭环 - 知识库状态")
    print("=" * 60)
    stats = mobius_loop.get_loop_stats()
    print(f"\n📊 当前知识库状态:")
    print(f"   - 总闭环迭代次数: {stats['total_loops']}")
    print(f"   - 爆款知识库文档数: {stats['hot_products_count']}")
    print(f"   - 投放策略库文档数: {stats['ad_strategies_count']}")
    print(f"   - 客服FAQ库文档数: {stats['faqs_count']}")
    print("\n💡 自反馈闭环流程:")
    print("   1. Agent 生成结果 → 2. 质量门控评估 → 3. 相似度去重")
    print("   4. 优质结果向量化入库 → 5. 下次 RAG 检索更精准")
    return stats


def run_full():
    print_banner()
    print("\n🚀 开始完整运营流程...\n")
    print("\n📦 [1/4] 选品Agent...")
    product_selection_agent.analyze_category("无线蓝牙耳机")
    print("\n📈 [2/4] 投放优化Agent...")
    ad_optimization_agent.optimize_campaigns(top_n=10)
    print("\n💬 [3/4] 多语言客服Agent...")
    customer_service_agent.handle_review("The product is terrible, broke after one day use!", 1)
    print("\n🔄 [4/4] 自反馈闭环统计...")
    stats = mobius_loop.get_loop_stats()
    print("\n" + "=" * 60)
    print("🎉 完整运营流程完成！")
    print("=" * 60)
    print(f"📊 闭环迭代次数: {stats['total_loops']}")
    print(f"📚 知识库总文档数: {stats['hot_products_count'] + stats['ad_strategies_count'] + stats['faqs_count']}")


def interactive_mode():
    print_banner()
    print("请选择要运行的模块：")
    print("  1. 选品Agent（淘宝商品分析）")
    print("  2. 投放优化Agent（淘宝联盟推广优化）")
    print("  3. 多语言客服Agent（差评/私信回复）")
    print("  4. 自反馈闭环统计")
    print("  5. 完整流程（全部模块）")
    print("  0. 退出")
    while True:
        choice = input("\n请输入序号: ").strip()
        if choice == "1":
            run_product_selection()
        elif choice == "2":
            run_ad_optimization()
        elif choice == "3":
            run_customer_service()
        elif choice == "4":
            run_loop_stats()
        elif choice == "5":
            run_full()
        elif choice == "0":
            print("👋 已退出")
            break
        else:
            print("无效输入，请重新选择")


def main():
    try:
        settings.validate()  # 真实店铺运营模式：淘宝三要素 + DeepSeek Key 必填
        interactive_mode()
    except KeyboardInterrupt:
        print("\n\n👋 程序已中断")
    except RuntimeError as e:
        print("\n❌ 配置校验失败：")
        print(f"   {e}")
        print("\n请参考 .env.example 创建 .env 并填写必要配置后重试。")
    except Exception as e:
        logger.error(f"程序运行出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()