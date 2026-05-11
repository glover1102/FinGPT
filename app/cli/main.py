import argparse
import os
import sys
import traceback
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.schemas.request import AnalysisRequest, UniversalRequest
from core.schemas.topic import TopicRequest
from pipelines.orchestration.dispatch import dispatch
from pipelines.orchestration.research_pipeline import run_pipeline
from pipelines.orchestration.topic_pipeline import run_topic_pipeline
from core.utils.logger import get_logger

logger = get_logger("cli.main")

def parse_args():
    parser = argparse.ArgumentParser(description="FinGPT Local Financial Research Assistant")
    parser.add_argument("--ticker", type=str, required=False, help="Stock ticker symbol to analyze")
    parser.add_argument("--topic", type=str, required=False, help="Force topic mode with the given theme")
    parser.add_argument("--related-ticker", action="append", default=[], help="Related ticker/proxy to include in topic mode. Can be supplied multiple times.")
    parser.add_argument("--question", type=str, required=True, help="Question to answer using the research pipeline")
    parser.add_argument("--sources", type=str, nargs="+", default=["news", "transcript"], help="Sources to pull data from")
    parser.add_argument("--lookback-days", type=int, default=60, help="Number of past days for data retrieval (default: 60)")
    parser.add_argument("--top-k", type=int, default=10, help="Number of document chunks to retrieve (default: 10)")
    parser.add_argument(
        "--model",
        type=str,
        default="qwen",
        choices=["qwen", "mistral", "ollama", "primary", "fingpt", "llama-2", "gemma4", "gemma", "gemma-experimental"],
        help="Inference route. Production baseline is qwen2.5; gemma4 is an explicit experimental option.",
    )
    parser.add_argument("--output-dir", type=str, default=None, help="Directory to save outputs")
    simulation_group = parser.add_mutually_exclusive_group()
    simulation_group.add_argument(
        "--simulate",
        action="store_true",
        help="Enable the optional scenario simulation layer for this CLI run.",
    )
    simulation_group.add_argument(
        "--no-simulate",
        action="store_true",
        help="Disable the optional scenario simulation layer for this CLI run.",
    )
    
    return parser.parse_args()

def main():
    args = parse_args()
    scenario_override = True if args.simulate else False if args.no_simulate else None
    if args.simulate:
        os.environ["SCENARIO_SIMULATION_ENABLED"] = "true"
    elif args.no_simulate:
        os.environ["SCENARIO_SIMULATION_ENABLED"] = "false"
    logger.info("Starting research pipeline")
    
    try:
        if args.topic:
            response = run_topic_pipeline(
                TopicRequest(
                    question=args.question,
                    theme=args.topic,
                    related_tickers=[ticker.upper() for ticker in (args.related_ticker or [])],
                    lookback_days=args.lookback_days,
                    top_k=args.top_k,
                    model=args.model,
                    output_dir=args.output_dir,
                    scenario_simulation_enabled=scenario_override,
                ),
                mode="sector_macro",
            )
            logger.info(f"Topic pipeline completed. Thesis: {response.core_thesis}")
        elif args.ticker:
            request = AnalysisRequest(
                ticker=args.ticker.upper(),
                question=args.question,
                sources=args.sources,
                lookback_days=args.lookback_days,
                top_k=args.top_k,
                model=args.model,
                output_dir=args.output_dir,
                scenario_simulation_enabled=scenario_override,
            )
            response = run_pipeline(request)
            logger.info(f"Pipeline completed successfully. Conclusion: {response.conclusion}")
        else:
            response = dispatch(
                UniversalRequest(
                    question=args.question,
                    mode_hint="auto",
                    sources=args.sources,
                    lookback_days=args.lookback_days,
                    top_k=args.top_k,
                    model=args.model,
                    output_dir=args.output_dir,
                    scenario_simulation_enabled=scenario_override,
                )
            )
            logger.info(f"Universal pipeline completed. Status: {response.status}")
        
    except Exception as e:
        logger.error(f"Execution failed: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
