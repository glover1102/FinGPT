import argparse
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
        choices=["qwen", "mistral", "ollama", "primary", "fingpt", "llama-2", "gemma", "gemma-experimental"],
        help="Inference route. Production baseline is qwen2.5; gemma is experimental only.",
    )
    parser.add_argument("--output-dir", type=str, default=None, help="Directory to save outputs")
    
    return parser.parse_args()

def main():
    args = parse_args()
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
                output_dir=args.output_dir
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
                )
            )
            logger.info(f"Universal pipeline completed. Status: {response.status}")
        
    except Exception as e:
        logger.error(f"Execution failed: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
