# Contribution-first schedule — implemented

The user approved contribution-first setup, superseding the earlier payout-first rounding proposal. The Next.js wizard accepts a fixed contribution per member per bank debit. `CircleInput` derives payout from this fixed minor-unit amount multiplied by actual debit dates in the full rotation. The authenticated preview validates funding before the user reviews the draft.

For matching frequencies the number of debit dates equals the planned members. For weekly/monthly mixed schedules, actual debit windows can contain 5/4/4 dates; every debit remains identical, and earlier surplus carries to later payouts. Each recipient receives the same derived payout. Anchors that cannot fund an early payout are rejected with an explanatory error. Fees remain separately accounted for.

The existing completed Shared milestones demo and historical signed agreements are immutable. Legacy payout-based inputs remain supported for sandbox fixtures and historical contracts; new native UI sends only contribution_minor. Live creation requires contribution-first input.

Coverage: equal mixed-frequency debits, odd member counts without rounding, mismatched client targets, unfunded first windows and a complete signed sandbox rotation with lifetime contributions equal to payouts.
