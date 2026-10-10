import { useQuery } from '@tanstack/react-query';
import { fetchStrategyTradebook } from '@/api/strategy_module';
import { Badge } from '@/components/ui/badge';
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from '@/components/ui/card';
import { Table, TableHeader, TableBody, TableRow, TableCell, TableHead } from '@/components/ui/table';
import { cn } from '@/lib/utils';
import { formatPnl, formatPrice } from '@/utils/formatters';

interface ClosedPositionsTabProps {
  strategyId: number;
}

export function ClosedPositionsTab({ strategyId }: ClosedPositionsTabProps) {
  const { data: trades, isLoading, error } = useQuery({
    queryKey: ['strategyTradebook', strategyId],
    queryFn: () => fetchStrategyTradebook(strategyId),
  });

  if (isLoading) {
    return <p className="py-6 text-center text-sm text-muted-foreground">Loading…</p>;
  }
  if (error) {
    return <p className="py-6 text-center text-sm text-muted-foreground">Error loading closed trades.</p>;
  }

  const closedTrades = ((trades as any[]) ?? []).filter(
    (t: any) => t.status === 'complete' && t.exit_avg != null
  );

  if (closedTrades.length === 0) {
    return <p className="py-6 text-center text-sm text-muted-foreground">No closed trades today</p>;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Closed Positions</CardTitle>
        <CardDescription>All completed trades for this strategy.</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Strategy</TableHead>
                <TableHead>Symbol</TableHead>
                <TableHead>Side</TableHead>
                <TableHead>Qty</TableHead>
                <TableHead className="text-right">Entry Avg</TableHead>
                <TableHead className="text-right">Exit Avg</TableHead>
                <TableHead className="text-right">Entry Time</TableHead>
                <TableHead className="text-right">Exit Time</TableHead>
                <TableHead className="text-right">Realized P&amp;L</TableHead>
                <TableHead className="text-right">Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {closedTrades.map((trade: any, idx: number) => (
                <TableRow key={`${trade.symbol}-${trade.exchange}-${trade.product}-${idx}`}>
                  <TableCell>
                    <Badge variant="outline" className="text-xs">
                      {trade.strategy ?? 'Manual / Unattributed'}
                    </Badge>
                  </TableCell>
                  <TableCell>{trade.symbol}</TableCell>
                  <TableCell>{trade.side?.toUpperCase() ?? '—'}</TableCell>
                  <TableCell className="font-mono text-right">
                    {trade.qty != null ? trade.qty : '—'}
                  </TableCell>
                  <TableCell className="font-mono text-right">
                    {trade.entry_avg != null ? formatPrice(trade.entry_avg) : '—'}
                  </TableCell>
                  <TableCell className="font-mono text-right">
                    {trade.exit_avg != null ? formatPrice(trade.exit_avg) : '—'}
                  </TableCell>
                  <TableCell className="font-mono text-right">
                    {trade.entry_time != null ? String(trade.entry_time) : '—'}
                  </TableCell>
                  <TableCell className="font-mono text-right">
                    {trade.exit_time != null ? String(trade.exit_time) : '—'}
                  </TableCell>
                  <TableCell className={cn('font-mono text-right', trade.realized_pnl < 0 ? 'text-destructive' : 'text-success')}>
                    {trade.realized_pnl != null ? formatPnl(trade.realized_pnl) : '—'}
                  </TableCell>
                  <TableCell>
                    <Badge variant="default" className="text-xs">CLOSED</Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}
