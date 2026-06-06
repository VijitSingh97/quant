"""Position-sizing calculator: vol target + fractional Kelly.

Two questions this answers:
  1. Given a target portfolio vol and a position's estimated vol, how big should it be?
  2. Given a strategy's win rate and payoff ratio, what fraction of capital is sane?

Defaults illustrate the filtered condor (high win rate, small-win/big-loss payoff).
Run:  python3 -m basis.size [--target-vol 0.15] [--position-vol 0.6]
                            [--win-prob 0.85] [--win-loss 0.30] [--kelly-frac 0.25]
"""

import argparse

from .core import fmt_pct, fmt_vol, vol_target_scale, kelly_fraction, fractional_kelly


def run(target_vol=0.15, position_vol=0.60, win_prob=0.85, win_loss=0.30,
        kelly_frac=0.25, cap=0.50):
    bar = "=" * 66
    print(f"\n{bar}\nPOSITION SIZER\n{bar}")

    scale = vol_target_scale(target_vol, position_vol)
    print(f"\nVOL TARGET")
    print(f"  target {fmt_vol(target_vol)}  /  position vol {fmt_vol(position_vol)}")
    print(f"  -> scale position to {scale:.2f}x  (deploy {fmt_pct(scale)} of 1-unit notional)")
    print(f"     rule of thumb: if realized vol doubles to {fmt_vol(position_vol*2)}, "
          f"size halves to {vol_target_scale(target_vol, position_vol*2):.2f}x.")

    full = kelly_fraction(win_prob, win_loss)
    frac = fractional_kelly(win_prob, win_loss, kelly_frac, cap)
    print(f"\nFRACTIONAL KELLY")
    print(f"  win prob {fmt_pct(win_prob)}   win/loss payoff ratio {win_loss:.2f}")
    print(f"  full Kelly {fmt_pct(full)}  ->  {kelly_frac:.0%}-Kelly (capped {cap:.0%}) = "
          f"risk {fmt_pct(frac)} of capital per bet")
    if full <= 0:
        print("  (full Kelly <= 0: no edge at these inputs — don't bet.)")

    print(f"\nREAD")
    print(f"• Size to a fixed $-risk, not fixed notional: at higher vol you hold less.")
    print(f"• Quarter-Kelly is the default for a reason — full Kelly assumes you know the")
    print(f"  edge exactly and ignores fat tails. For a capped-loss condor, risk ~{fmt_pct(frac)}/roll")
    print(f"  means one max-loss costs that much — survivable, and you compound the wins.")
    print("\n(Educational tooling, not investment advice.)")


def main():
    ap = argparse.ArgumentParser(description="Vol-target + fractional-Kelly position sizer")
    ap.add_argument("--target-vol", type=float, default=0.15)
    ap.add_argument("--position-vol", type=float, default=0.60)
    ap.add_argument("--win-prob", type=float, default=0.85)
    ap.add_argument("--win-loss", type=float, default=0.30)
    ap.add_argument("--kelly-frac", type=float, default=0.25)
    args = ap.parse_args()
    run(target_vol=args.target_vol, position_vol=args.position_vol,
        win_prob=args.win_prob, win_loss=args.win_loss, kelly_frac=args.kelly_frac)


if __name__ == "__main__":
    main()
