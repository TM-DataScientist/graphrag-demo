import argparse
import asyncio
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from dotenv import dotenv_values
from lightrag import LightRAG, QueryParam
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc


# このスクリプトは「ragtest/.env に入っている API キーをそのまま使い、
# ルートの book.txt を LightRAG で索引化して README 相当の query を実行する」
# ことだけに絞った最小構成。
# デフォルト値をリポジトリ構成に寄せておくことで、引数なしでも再現できる。
ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_ENV_PATH = ROOT_DIR / "ragtest" / ".env"
DEFAULT_INPUT_PATH = ROOT_DIR / "book.txt"
DEFAULT_WORKING_DIR = ROOT_DIR / "dickens"
DEFAULT_QUERY = "What are the top themes in this story?"
DEFAULT_LLM_MODEL = "gpt-5.4-nano"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-large"


def parse_args() -> argparse.Namespace:
    """CLI 引数を定義する。

    既定値だけで実行できるようにしているが、入力ファイルや working_dir を
    差し替えたい場合はここから上書きできる。
    """
    parser = argparse.ArgumentParser(
        description="Run a minimal LightRAG pipeline using ragtest/.env and book.txt."
    )
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_PATH),
        help="Path to the env file that contains GRAPHRAG_API_KEY.",
    )
    parser.add_argument(
        "--input-file",
        default=str(DEFAULT_INPUT_PATH),
        help="Path to the text file to ingest.",
    )
    parser.add_argument(
        "--working-dir",
        default=str(DEFAULT_WORKING_DIR),
        help="Directory used for the LightRAG working set.",
    )
    parser.add_argument(
        "--query",
        default=DEFAULT_QUERY,
        help="Question to run after indexing.",
    )
    parser.add_argument(
        "--mode",
        default="global",
        choices=["naive", "local", "global", "hybrid", "mix", "bypass"],
        help="LightRAG query mode.",
    )
    parser.add_argument(
        "--llm-model",
        default=DEFAULT_LLM_MODEL,
        help="Chat model used by LightRAG.",
    )
    parser.add_argument(
        "--embedding-model",
        default=DEFAULT_EMBEDDING_MODEL,
        help="Embedding model used by LightRAG.",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Delete the working directory and rebuild the LightRAG index.",
    )
    return parser.parse_args()


def ensure_utf8_stdout() -> None:
    """Windows 端末の文字化けを避けるため、標準出力を UTF-8 に固定する。

    LightRAG / LLM の回答には cp932 で表現できない文字が混ざることがある。
    そのまま print すると最後の出力時に落ちるので、最初に stdout/stderr を
    UTF-8 に寄せておく。
    """
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")


def resolve_repo_path(path_str: str) -> Path:
    """相対パスをリポジトリ基準の絶対パスに解決する。

    実行ディレクトリがどこであっても、`book.txt` や `ragtest/.env` を
    同じ基準で見つけられるようにするための補助関数。
    """
    path = Path(path_str)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path.resolve()


def load_api_key(env_path: Path) -> str:
    """env ファイルから API キーを取り出す。

    このリポジトリでは GraphRAG 用に `GRAPHRAG_API_KEY` を持っているので、
    LightRAG 専用の `API_KEY` が無くても流用できるようにしている。
    """
    config = dotenv_values(env_path)
    api_key = config.get("GRAPHRAG_API_KEY") or config.get("API_KEY")
    if not api_key:
        raise ValueError(f"No API key found in {env_path}")
    return api_key


def workdir_has_failed_state(workdir: Path) -> bool:
    """既存の working_dir が壊れていないかを判定する。

    LightRAG は途中失敗した状態のファイルが残ると、その後の再実行で
    中途半端なキャッシュやステータスを再利用してしまうことがある。
    そのため、以下のケースは「作り直した方が安全」とみなす。

    - working_dir はあるが状態ファイルがない
    - 状態ファイルが壊れていて JSON として読めない
    - 状態ファイルはあるが中身が空
    - どれかの文書ステータスが failed になっている
    """
    status_path = workdir / "kv_store_doc_status.json"
    if not workdir.exists():
        return False
    if not status_path.exists():
        # 状態ファイルがないのに中身だけある場合は、前回の処理が不完全だった
        # 可能性が高いので安全側に倒して作り直す。
        return any(workdir.iterdir())
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # JSON が壊れている時点で再利用価値がないので再作成。
        return True
    if not payload:
        return True
    return any(item.get("status") == "failed" for item in payload.values())


def safe_reset_workdir(workdir: Path) -> None:
    """working_dir を削除して初期化し直せる状態に戻す。

    `--working-dir` を自由に受ける以上、誤ったパスを再帰削除しないように
    「このリポジトリ配下であること」を確認してから消す。
    """
    if not workdir.exists():
        return
    if ROOT_DIR not in workdir.parents:
        raise ValueError(f"Refusing to delete path outside repository: {workdir}")
    shutil.rmtree(workdir)


def make_llm_model_func(api_key: str, model: str):
    """LightRAG に渡す LLM 呼び出し関数を組み立てる。

    LightRAG は「prompt, system_prompt, history_messages を受ける coroutine」
    を期待している。ここで OpenAI 用ヘルパーをその形に包んでおくと、
    後段では `LightRAG(...)` にそのまま差し込める。
    """
    async def llm_model_func(
        prompt: str,
        system_prompt: str | None = None,
        history_messages: list[dict] | None = None,
        **kwargs,
    ) -> str:
        return await openai_complete_if_cache(
            model,
            prompt,
            system_prompt=system_prompt,
            history_messages=history_messages or [],
            api_key=api_key,
            **kwargs,
        )

    return llm_model_func


def make_embedding_func(api_key: str, model: str) -> EmbeddingFunc:
    """LightRAG 用の埋め込み関数を作る。

    `lightrag.llm.openai.openai_embed` は既に EmbeddingFunc でラップ済みだが、
    そのままさらに包むと、LightRAG 側のベクトル本数チェックと噛み合わず
    `expected N vectors but got 2N` のような不一致が起きることがあった。

    そのため、ここでは `.func` で生の embedding 関数を取り出し、
    `text-embedding-3-large` の次元数 3072 を明示した新しい EmbeddingFunc として
    もう一度組み直している。
    """
    raw_openai_embed = openai_embed.func

    async def embedding_func(texts: list[str], **kwargs) -> np.ndarray:
        return await raw_openai_embed(
            texts,
            model=model,
            api_key=api_key,
            **kwargs,
        )

    return EmbeddingFunc(
        # OpenAI の `text-embedding-3-large` は 3072 次元。
        # ここがずれると LightRAG の内部検証で落ちる。
        embedding_dim=3072,
        # 1 テキストあたりの切り詰め上限。
        # 長文を丸ごと投げたときに embedding API 側で失敗しないようにする。
        max_token_size=8192,
        func=embedding_func,
    )


async def run_query(args: argparse.Namespace) -> str:
    """索引化と query 実行の本体。

    実行順は以下。
    1. 引数のパスを絶対パスに解決
    2. 以前の失敗状態が残っていれば working_dir を削除
    3. env から API キーを読み込み、LLM/Embedding 関数を作成
    4. LightRAG を初期化
    5. 初回のみ book.txt を ingest して索引作成
    6. query を実行して回答文字列を返す
    7. 最後に必ず storage を close
    """
    env_path = resolve_repo_path(args.env_file)
    input_path = resolve_repo_path(args.input_file)
    working_dir = resolve_repo_path(args.working_dir)

    # 明示的に `--rebuild` が指定された場合だけでなく、
    # 前回失敗した working_dir が見つかった場合も自動で作り直す。
    if args.rebuild or workdir_has_failed_state(working_dir):
        safe_reset_workdir(working_dir)

    api_key = load_api_key(env_path)
    llm_model_func = make_llm_model_func(api_key, args.llm_model)
    embedding_func = make_embedding_func(api_key, args.embedding_model)

    # README 相当の最小構成なので、ローカル完結しやすい NetworkXStorage を使う。
    # Neo4j などの外部依存はここでは増やさない。
    rag = LightRAG(
        working_dir=str(working_dir),
        graph_storage="NetworkXStorage",
        llm_model_func=llm_model_func,
        llm_model_name=args.llm_model,
        # 過度な並列は API 制限に引っかかりやすいので、そこまで攻めない設定にする。
        llm_model_max_async=4,
        embedding_func=embedding_func,
        embedding_batch_num=10,
        embedding_func_max_async=4,
        # GraphRAG 側の設定と近い粒度に寄せて、比較しやすくする。
        chunk_token_size=1200,
        chunk_overlap_token_size=100,
    )

    await rag.initialize_storages()
    try:
        # 初回実行時は working_dir が空なので、book.txt を ingest して索引を作る。
        # 2 回目以降は既存インデックスを再利用し、query だけを実行する。
        if not working_dir.exists() or not any(working_dir.iterdir()):
            content = input_path.read_text(encoding="utf-8")
            await rag.ainsert(content, file_paths=str(input_path))

        answer = await rag.aquery(
            # README 相当の問い合わせを、指定モードでそのまま流す。
            args.query,
            param=QueryParam(mode=args.mode),
        )
        return answer
    finally:
        # 途中で例外が起きても、LightRAG の各種 storage は必ず close する。
        # これを怠ると次回実行時に中途半端な状態が残りやすい。
        await rag.finalize_storages()


def main() -> None:
    """CLI エントリポイント。"""
    ensure_utf8_stdout()
    args = parse_args()
    answer = asyncio.run(run_query(args))
    print(answer)


if __name__ == "__main__":
    main()
