# Wide Refactors

Ticket it as **expand–contract**:

1. **Expand:** add the new form beside the old.
2. **Migrate:** move callers in batches sized by blast radius. Each batch is blocked by the expand ticket and must keep CI green.
3. **Contract:** delete the old form after every migration ticket lands.

When no migration batch can stay green alone, use an integration branch and make every batch block one final integrate-and-verify ticket. Green is promised there.
