from __future__ import annotations

import argparse
import getpass
import json
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from papertrade.config import Settings
from papertrade.db import Database
from papertrade.domain import INSTRUMENTS
from papertrade.logging import configure_logging


def output(value):
    print(json.dumps(value, indent=2, default=str, allow_nan=False))


def main():
    parser = argparse.ArgumentParser(description="Paper-only multi-market research and execution")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init-db", "run-once", "monitor-once", "scheduler", "status", "verify-brokers", "hash-password",
                 "analyze-ai", "ai-status"):
        commands.add_parser(name)
    ai_models = commands.add_parser("ai-models")
    ai_models.add_argument("--provider", choices=["groq", "hermes"])
    compare = commands.add_parser("compare-strategies")
    compare.add_argument("symbol", choices=INSTRUMENTS)
    compare.add_argument("--model", help="Quant model version; defaults to the active version when present")
    approve_strategy = commands.add_parser("approve-strategy")
    approve_strategy.add_argument("id", type=int)
    serve = commands.add_parser("serve")
    serve.add_argument("--host", choices=["127.0.0.1", "0.0.0.0"], default="127.0.0.1")
    commands.add_parser("dashboard")
    collect = commands.add_parser("collect")
    collect.add_argument("symbol", choices=INSTRUMENTS)
    collect.add_argument("--start", required=True)
    collect.add_argument("--end", required=True)
    train = commands.add_parser("train")
    train.add_argument("symbol", choices=INSTRUMENTS)
    train.add_argument("--params", default="{}", help="JSON of documented LightGBM hyperparameters")
    backtest = commands.add_parser("backtest")
    backtest.add_argument("symbol", choices=INSTRUMENTS)
    backtest.add_argument("--model")
    promote = commands.add_parser("promote")
    promote.add_argument("symbol", choices=INSTRUMENTS)
    promote.add_argument("version")
    control = commands.add_parser("control")
    control.add_argument("action", choices=["pause", "resume", "kill", "close_all", "enable_market", "disable_market"])
    control.add_argument("--market", choices=["crypto", "equity", "forex"])
    args = parser.parse_args()
    settings = Settings()
    configure_logging(settings)
    db = Database(settings)
    try:
        if args.command == "hash-password":
            from papertrade.security import password_hasher
            print(password_hasher.hash(getpass.getpass("Dashboard password: ")))
        elif args.command == "init-db":
            from alembic import command
            from alembic.config import Config
            config_path = Path("alembic.ini").resolve()
            if not config_path.is_file():
                raise ValueError("Run init-db from the repository root containing alembic.ini")
            command.upgrade(Config(str(config_path)), "head")
            db.seed()
            output({"database": "initialized", "mode": "paper"})
        elif args.command == "serve":
            import uvicorn
            from papertrade.api import create_app
            uvicorn.run(create_app(settings, db), host=args.host, port=8000, access_log=False, log_config=None,
                        proxy_headers=True, forwarded_allow_ips="127.0.0.1,::1")
        elif args.command == "dashboard":
            import subprocess
            dashboard = Path(__file__).with_name("dashboard.py")
            raise SystemExit(subprocess.call([sys.executable, "-m", "streamlit", "run", str(dashboard),
                "--server.address=127.0.0.1", "--server.port=8501", "--server.headless=true"]))
        elif args.command == "status":
            from papertrade.monitoring import system_status
            output(system_status(db))
        elif args.command in {"analyze-ai", "ai-status", "ai-models"}:
            from papertrade.ai.service import AIService, make_provider
            if args.command == "ai-models" and args.provider:
                settings = settings.model_copy(update={"ai_provider": args.provider})
            service = AIService(settings, db)
            if args.command == "analyze-ai":
                output(service.run_once())
            elif args.command == "ai-status":
                from papertrade.monitoring import system_status
                output(system_status(db)["ai"])
            else:
                provider = make_provider(settings, service.budget, discovery=True)
                output({"provider": provider.name, "models": provider.get_models(),
                        "note": "Availability does not establish free billing entitlement or strategy validation"})
        elif args.command in {"compare-strategies", "approve-strategy"}:
            from papertrade.ai.evaluation import approve_certificate, build_certificate, evaluate_strategies
            from papertrade.ai.fusion import strategy_policy
            from papertrade.ai.service import model_for
            from papertrade.db import aware
            from papertrade.domain import utcnow
            from papertrade.models import AuditLog, ModelVersion, StrategyObservation, StrategyValidation
            import hashlib
            if args.command == "compare-strategies":
                with db.session() as session:
                    model_rows = session.scalars(select(ModelVersion).where(ModelVersion.symbol == args.symbol)).all()
                    version = args.model or next((m.version for m in model_rows if m.active), None)
                    query = select(StrategyObservation).where(StrategyObservation.symbol == args.symbol)
                    if version:
                        query = query.where(StrategyObservation.model_version == version)
                    rows = session.scalars(query.order_by(StrategyObservation.candle_at)).all()
                    models = {m.version: m.metrics for m in model_rows}
                observations = []
                for row in rows:
                    value = {column.name: getattr(row, column.name) for column in StrategyObservation.__table__.columns}
                    for key, item in list(value.items()):
                        if isinstance(item, datetime):
                            value[key] = aware(item).isoformat()
                    metadata = models.get(row.model_version, {})
                    value.update(quant_data_end=metadata.get("data_end"), quant_trained_at=metadata.get("trained_at"),
                                 quant_threshold=metadata.get("threshold"), quant_model_accepted=metadata.get("accepted"),
                                 quant_horizon_bars=metadata.get("horizon"))
                    observations.append(value)
                report = evaluate_strategies(db.load_candles(args.symbol), observations, INSTRUMENTS[args.symbol], settings)
                folder = settings.state_dir / "strategy_reports"
                folder.mkdir(parents=True, exist_ok=True)
                now = utcnow()
                path = folder / f"{args.symbol.replace('/', '_')}_{now.strftime('%Y%m%dT%H%M%S')}.json"
                path.write_text(json.dumps(report, indent=2, allow_nan=False))
                candidates = []
                with db.session() as session:
                    for name in ("quant_only", "ai_filtered_quant", "hybrid"):
                        certificate = build_certificate(report, name, report["quant_model_version"], report["ai_provider"],
                                                        report["ai_model"], settings, now)
                        row = StrategyValidation(strategy=name, symbol=args.symbol, quant_model_version=report["quant_model_version"],
                            provider=report["ai_provider"], ai_model=report["ai_model"], policy_hash=report["policy_sha256"],
                            created_at=now, expires_at=datetime.fromisoformat(certificate["expires_at"]), accepted=certificate["accepted"],
                            approved=False, source=report["source"], report=report, certificate=certificate)
                        session.add(row)
                        session.flush()
                        candidates.append({"id": row.id, "strategy": name, "accepted": row.accepted, "approved": False})
                    session.add(AuditLog(actor="local-cli", action="strategy_compared", detail={"symbol": args.symbol, "report": str(path)}))
                output({"report": str(path), "candidates": candidates})
            else:
                from filelock import FileLock
                with FileLock(settings.state_dir / "engine.lock", timeout=30):
                    with db.session() as session:
                        row = session.get(StrategyValidation, args.id)
                        if row is None:
                            raise ValueError("Unknown strategy validation ID")
                        digest = hashlib.sha256(json.dumps(row.report, sort_keys=True, allow_nan=False).encode()).hexdigest()
                        if (row.policy_hash != strategy_policy(settings)["sha256"] or
                            row.certificate.get("report_sha256") != digest or
                            row.provider != settings.ai_provider or row.ai_model != model_for(settings)):
                            raise ValueError("Strategy report or current provider/policy does not match")
                        row.certificate = approve_certificate(row.certificate)
                        row.approved = True
                        session.add(AuditLog(actor="local-cli", action="strategy_approved", detail={"validation_id": row.id}))
                output({"validation_id": args.id, "approved": True,
                        "note": "Select this strategy and explicitly enable paper execution; risk controls remain mandatory"})
        elif args.command in {"collect", "train", "backtest", "promote"}:
            from papertrade.models import AuditLog, FeatureMetadata, ModelVersion
            from papertrade.ml import backtest_saved_model, promote_model, train_model
            instrument = INSTRUMENTS[args.symbol]
            if args.command == "collect":
                from papertrade.data import collect_history
                from papertrade.engine import TradingEngine
                start = datetime.fromisoformat(args.start.replace("Z", "+00:00"))
                end = datetime.fromisoformat(args.end.replace("Z", "+00:00"))
                if start.tzinfo is None or end.tzinfo is None:
                    raise ValueError("Historical intervals must include UTC timezone")
                engine = TradingEngine(settings, db)
                source = engine.sources.get(instrument.market)
                if source is None:
                    raise ValueError("Provider credentials required for this market")
                candles = collect_history(args.symbol, start, end, settings, broker=source)
                db.store_candles(args.symbol, candles, type(source).__name__)
                output({"symbol": args.symbol, "rows": len(candles), "start": candles.index[0],
                        "end": candles.index[-1], "source": type(source).__name__})
            elif args.command == "train":
                from papertrade.features import FEATURE_VERSION, build_features
                candles = db.load_candles(args.symbol)
                metadata = train_model(candles, instrument, settings, params=json.loads(args.params))
                with db.session() as session:
                    existing = session.scalar(select(ModelVersion).where(ModelVersion.symbol == args.symbol,
                                                        ModelVersion.version == metadata["version"]))
                    if existing is None:
                        session.add(ModelVersion(symbol=args.symbol, version=metadata["version"],
                            accepted=metadata["accepted"], active=False, metrics=metadata))
                    session.add(FeatureMetadata(symbol=args.symbol, version=FEATURE_VERSION,
                                                columns={"columns": list(build_features(candles).columns)}))
                    session.add(AuditLog(actor="local-cli", action="model_trained", detail={
                        "symbol": args.symbol, "version": metadata["version"], "accepted": metadata["accepted"]}))
                output(metadata)
            elif args.command == "promote":
                # Serialize pointer updates against inference and durable order validation.
                from filelock import FileLock
                with FileLock(settings.state_dir / "engine.lock", timeout=30):
                    metadata = promote_model(args.symbol, args.version, settings)
                    with db.session() as session:
                        rows = session.scalars(select(ModelVersion).where(ModelVersion.symbol == args.symbol)).all()
                        for row in rows:
                            row.active = row.version == args.version
                        if not any(row.version == args.version for row in rows):
                            session.add(ModelVersion(symbol=args.symbol, version=args.version, active=True,
                                                     accepted=True, metrics=metadata))
                        session.add(AuditLog(actor="local-cli", action="model_promoted",
                                             detail={"symbol": args.symbol, "version": args.version}))
                output({"active_model": args.version, "symbol": args.symbol})
            else:
                report = backtest_saved_model(db.load_candles(args.symbol), instrument, settings, args.model)
                folder = settings.state_dir / "backtests"
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / f"{args.symbol.replace('/', '_')}_{report['model_version']}.json"
                path.write_text(json.dumps(report, indent=2, default=str, allow_nan=False))
                output({"report": str(path), "metrics": report["metrics"], "period": report["period"],
                        "previously_used_for_acceptance": report["previously_used_for_acceptance"]})
        else:
            from papertrade.engine import TradingEngine
            engine = TradingEngine(settings, db)
            if args.command == "run-once":
                result = engine.run_once()
                output(result)
                if result["status"] in {"degraded", "failed"}:
                    raise SystemExit(1)
            elif args.command == "monitor-once":
                if not engine.monitor_once():
                    raise SystemExit(1)
            elif args.command == "scheduler":
                from papertrade.scheduler import run_scheduler
                run_scheduler(engine)
            elif args.command == "control":
                output(engine.control(args.action, args.market, actor="local-cli"))
            elif args.command == "verify-brokers":
                report = {name: {"status": "disabled", "reason": reason} for name, reason in engine.disabled.items()}
                for name, broker in engine.brokers.items():
                    try:
                        account = broker.get_account()
                        positions, orders = broker.get_positions(), broker.get_open_orders()
                        report[name] = {"connected": True, "mode": "local simulator" if name == "simulator" else "broker paper",
                            "currency": account.currency, "equity": account.equity, "cash": account.cash,
                            "trading_allowed": account.trading_allowed, "positions": len(positions), "open_orders": len(orders)}
                    except Exception as exc:
                        report[name] = {"connected": False, "reason": engine._error(exc)}
                output(report)
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as exc:
        # CLI must not accidentally print broker credentials through exception chains.
        from papertrade.domain import BrokerError
        from papertrade.data import DataError
        from papertrade.ml import ModelError
        from papertrade.ai.budget import BudgetExceeded
        from papertrade.ai.providers import ProviderError
        from papertrade.ai.schema import AIValidationError
        from papertrade.ai.service import AIDisabled
        from papertrade.logging import redact
        safe_error = isinstance(exc, (BrokerError, DataError, ModelError, AIDisabled, BudgetExceeded,
                                      ProviderError, AIValidationError))
        safe_strategy_error = args.command in {"compare-strategies", "approve-strategy"} and isinstance(exc, ValueError)
        detail = str(exc) if safe_error or safe_strategy_error else type(exc).__name__
        output({"error": redact(detail, settings), "mode": "paper"})
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
