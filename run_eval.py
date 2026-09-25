import asyncio
from app.eval.runner import benchmark_runner

async def main():
    print("=== Running NexusFlow AI Benchmark-30 Evaluation ===")
    summary = await benchmark_runner.run_all()
    print(f"Total Tasks: {summary['total_benchmarks']}")
    print(f"Passed: {summary['passed_count']} ({summary['pass_rate_pct']}%)")
    print(f"Failed: {summary['failed_count']}")
    print(f"Self-Healing: {summary['self_healed_count']}/{summary['self_healing_opportunities']} "
          f"({summary['self_healing_success_rate_pct']}%)")
    print(f"SafeGuard gates exercised: {summary['hitl_gates_observed']}")
    print(f"Measured agent time (all tasks): {summary['total_agent_time_sec']}s "
          f"(avg {summary['avg_agent_time_sec']}s)")
    print(f"Estimated manual baseline: {summary['total_simulated_manual_time_sec']}s")
    print(f"Average speedup (measured vs est.): {summary['average_speedup_factor']}x")
    print(f"Planning cost: ${summary['total_llm_cost_usd']} "
          f"(planner={summary['planner_mode']})")
    print(f"Engines: MCP={summary['mcp_transport']} - browser={summary['browser_engine']}")
    failures = [r for r in summary["results"] if r["status"] == "FAILED"]
    for r in failures:
        print(f"  ✗ {r['test_id']}: {r['notes']}")

if __name__ == "__main__":
    asyncio.run(main())

