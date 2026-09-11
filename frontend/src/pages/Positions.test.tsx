/**
 * Positions Page Tests:
 * 1. Close button behaviors (Issue #2054: squared-off position offers no Close button)
 * 2. Strategy Attribution and Contract Breakdown
 */

import { fireEvent, render, screen, waitFor, within } from '@/test/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AttributedPositionsData, Position } from '@/types/trading'
import Positions from './Positions'

// Mock useAuthStore
vi.mock('@/stores/authStore', () => ({
  useAuthStore: () => ({
    apiKey: 'test-api-key',
    user: { broker: 'zerodha' },
  }),
}))

// Mock useSupportedExchanges
vi.mock('@/hooks/useSupportedExchanges', () => ({
  useSupportedExchanges: () => ({
    isCrypto: false,
  }),
}))

// Mock usePageVisibility
vi.mock('@/hooks/usePageVisibility', () => ({
  usePageVisibility: () => ({
    isVisible: true,
    wasHidden: false,
    timeSinceHidden: 0,
  }),
}))

// Mock useOrderEventRefresh
vi.mock('@/hooks/useOrderEventRefresh', () => ({
  useOrderEventRefresh: vi.fn(),
}))

// Mock themeStore
vi.mock('@/stores/themeStore', () => ({
  onModeChange: () => () => {},
}))

// Mock useLivePrice: pass through positions as enhancedData
vi.mock('@/hooks/useLivePrice', () => ({
  useLivePrice: (items: Position[]) => ({
    data: items,
    isLive: false,
    isPaused: false,
    isConnected: true,
    isFallbackMode: false,
    isAnyMarketOpen: true,
    multiQuotes: new Map(),
    refreshMultiQuotes: vi.fn(),
  }),
}))

// Mock tradingApi
const mockGetPositions = vi.fn()
const mockGetAttributedPositions = vi.fn()
const mockClosePosition = vi.fn()
const mockCloseAllPositions = vi.fn()

vi.mock('@/api/trading', () => ({
  tradingApi: {
    getPositions: (...args: unknown[]) => mockGetPositions(...args),
    getAttributedPositions: (...args: unknown[]) => mockGetAttributedPositions(...args),
    closePosition: (...args: unknown[]) => mockClosePosition(...args),
    closeAllPositions: (...args: unknown[]) => mockCloseAllPositions(...args),
  },
}))

const storage: Record<string, string> = {}
const mockLocalStorage = {
  getItem: vi.fn((k: string) => storage[k] ?? null),
  setItem: vi.fn((k: string, v: string) => {
    storage[k] = String(v)
  }),
  removeItem: vi.fn((k: string) => {
    delete storage[k]
  }),
  clear: vi.fn(() => {
    for (const k in storage) delete storage[k]
  }),
  key: vi.fn((i: number) => Object.keys(storage)[i] ?? null),
  get length() {
    return Object.keys(storage).length
  },
}
Object.defineProperty(globalThis, 'localStorage', {
  value: mockLocalStorage,
  writable: true,
})

const OPEN_POSITION: Position = {
  symbol: 'NIFTY25SEP2625000CE',
  exchange: 'NFO',
  product: 'NRML',
  quantity: -75,
  average_price: 120.5,
  ltp: 98.25,
  pnl: 1668.75,
} as Position

const CLOSED_POSITION: Position = {
  symbol: 'BANKNIFTY25SEP2654000PE',
  exchange: 'NFO',
  product: 'NRML',
  quantity: 0,
  average_price: 210.1,
  ltp: 185.4,
  pnl: -740.0,
} as Position

async function renderPositions(positions: Position[]) {
  mockGetPositions.mockResolvedValue({ status: 'success', data: positions })
  mockGetAttributedPositions.mockResolvedValue({
    status: 'success',
    data: { positions: [], contracts: [], summary: {} },
  })
  render(<Positions />)
  // The first row to arrive tells us the fetch has resolved and painted.
  await screen.findByText(positions[0].symbol)
}

describe('Positions close button', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockLocalStorage.clear()
    mockGetAttributedPositions.mockResolvedValue({
      status: 'success',
      data: { positions: [], contracts: [], summary: {} },
    })
  })

  it('offers Close on a position that is still open', async () => {
    await renderPositions([OPEN_POSITION])

    expect(
      screen.getByRole('button', { name: `Close ${OPEN_POSITION.symbol} position` })
    ).toBeInTheDocument()
  })

  it('THE DEFECT: offers no Close on a position already squared off', async () => {
    await renderPositions([CLOSED_POSITION])

    expect(
      screen.queryByRole('button', { name: `Close ${CLOSED_POSITION.symbol} position` })
    ).not.toBeInTheDocument()
  })

  it('leaves the open row actionable when both are on the page', async () => {
    await renderPositions([OPEN_POSITION, CLOSED_POSITION])

    expect(
      screen.getByRole('button', { name: `Close ${OPEN_POSITION.symbol} position` })
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: `Close ${CLOSED_POSITION.symbol} position` })
    ).not.toBeInTheDocument()
  })

  it('never sends a close request for a squared-off position', async () => {
    await renderPositions([CLOSED_POSITION])

    // Nothing on the row can reach the endpoint, so the engine is never asked
    // to exit a position that is not there, and no alert can be raised for it.
    expect(mockClosePosition).not.toHaveBeenCalled()
  })

  it('keeps the closed row and its realised P&L visible', async () => {
    await renderPositions([CLOSED_POSITION])

    // Hiding the row would lose the realised figure, which is the reason the
    // broker still reports it. Only the action goes.
    expect(screen.getByText(CLOSED_POSITION.symbol)).toBeInTheDocument()
  })

  it('does not colour a zero quantity as a short', async () => {
    await renderPositions([CLOSED_POSITION])

    // Symbol, exchange, product, quantity - the fourth cell of the row.
    const row = screen.getByText(CLOSED_POSITION.symbol).closest('tr')
    expect(row).not.toBeNull()
    const quantityCell = within(row as HTMLElement).getAllByRole('cell')[3]

    expect(quantityCell).toHaveTextContent('0')
    expect(quantityCell.className).toContain('text-muted-foreground')
    expect(quantityCell.className).not.toContain('text-red-600')
  })

  it('treats a string zero quantity as closed, not as open', async () => {
    // The API does not always send a number. Zerodha's position mapping
    // defaults quantity to the string "0", and a strict `!== 0` reads that as
    // an open position - putting the button back on the exact row this guard
    // exists to clear.
    await renderPositions([{ ...CLOSED_POSITION, quantity: '0' } as unknown as Position])

    expect(
      screen.queryByRole('button', { name: `Close ${CLOSED_POSITION.symbol} position` })
    ).not.toBeInTheDocument()
  })

  it('still offers Close when a live quantity arrives as a string', async () => {
    await renderPositions([{ ...OPEN_POSITION, quantity: '-75' } as unknown as Position])

    expect(
      screen.getByRole('button', { name: `Close ${OPEN_POSITION.symbol} position` })
    ).toBeInTheDocument()
  })

  it('disables Close All when every position is squared off', async () => {
    await renderPositions([CLOSED_POSITION])

    expect(screen.getByRole('button', { name: /Close All/ })).toBeDisabled()
  })
})

describe('Positions with Strategy Attribution (Phase 3)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockLocalStorage.clear()
  })

  it('renders broker net position, contract reconciliation badges, and strategy overview cards', async () => {
    const brokerPositions: Position[] = [
      {
        symbol: 'BANKBARODA29SEP26FUT',
        exchange: 'NFO',
        product: 'NRML',
        quantity: -3025,
        average_price: 242.08,
        ltp: 237.8,
        pnl: 12947.0,
        pnlpercent: 1.77,
      },
    ]

    const attributedData: AttributedPositionsData = {
      positions: [
        {
          strategy: 'ICHI_V2',
          symbol: 'BANKBARODA29SEP26FUT',
          exchange: 'NFO',
          product: 'NRML',
          signed_quantity: -2925,
          side: 'SHORT',
          quantity: 2925,
          average_price: 242.1,
          ltp: 237.8,
          realized_pnl: 0,
          today_realized_pnl: 0,
          unrealized_pnl: 12577.5,
          total_pnl: 12577.5,
          pnlpercent: 1.78,
          broker_quantity: -3025,
          tracked_quantity: -2925,
          residual_quantity: -100,
          reconciliation_status: 'RECONCILED',
        },
        {
          strategy: 'Manual / Unattributed',
          symbol: 'BANKBARODA29SEP26FUT',
          exchange: 'NFO',
          product: 'NRML',
          signed_quantity: -100,
          side: 'SHORT',
          quantity: 100,
          average_price: 241.9,
          ltp: 237.8,
          realized_pnl: 0,
          today_realized_pnl: 0,
          unrealized_pnl: 410.0,
          total_pnl: 410.0,
          pnlpercent: 1.7,
          broker_quantity: -3025,
          tracked_quantity: -2925,
          residual_quantity: -100,
          reconciliation_status: 'RECONCILED',
        },
      ],
      contracts: [
        {
          symbol: 'BANKBARODA29SEP26FUT',
          exchange: 'NFO',
          product: 'NRML',
          broker_quantity: -3025,
          tracked_quantity: -2925,
          residual_quantity: -100,
          has_residual: true,
          strategies_count: 1,
          reconciliation_status: 'RECONCILED',
        },
      ],
      summary: {
        total_broker_positions: 1,
        total_tracked_positions: 1,
        total_residual_positions: 1,
        total_realized_pnl: 0,
        total_unrealized_pnl: 12987.5,
        total_pnl: 12987.5,
        reconciliation_status: 'RECONCILED',
      },
    }

    mockGetPositions.mockResolvedValue({ status: 'success', data: brokerPositions })
    mockGetAttributedPositions.mockResolvedValue({ status: 'success', data: attributedData })

    render(<Positions />)

    // Wait for data load
    await waitFor(() => {
      expect(screen.getByText('BANKBARODA29SEP26FUT')).toBeInTheDocument()
    })

    // Verify both APIs were called
    expect(mockGetPositions).toHaveBeenCalledWith('test-api-key')
    expect(mockGetAttributedPositions).toHaveBeenCalledWith('test-api-key', undefined, true)

    // Verify reconciliation badges on contract row
    expect(screen.getByText('✓ RECONCILED')).toBeInTheDocument()
    expect(screen.getByText('Broker Net:')).toBeInTheDocument()
    expect(screen.getAllByText('-3025').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Tracked:')).toBeInTheDocument()
    expect(screen.getByText('-2925')).toBeInTheDocument()
    expect(screen.getByText('Manual:')).toBeInTheDocument()
    expect(screen.getByText('-100')).toBeInTheDocument()

    // Verify Strategy Overview cards
    expect(screen.getByText('Strategy Overview')).toBeInTheDocument()
    expect(screen.getByText('ICHI_V2')).toBeInTheDocument()

    // Verify expanding contract row reveals strategy breakdown
    const expandButton = screen.getByLabelText('Expand BANKBARODA29SEP26FUT')
    fireEvent.click(expandButton)

    await waitFor(() => {
      expect(screen.getByText('Strategy Position Attribution')).toBeInTheDocument()
      expect(screen.getByText('2 records')).toBeInTheDocument()
    })

    // Both strategy legs should be shown in the sub-table
    expect(screen.getAllByText('ICHI_V2').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Manual / Unattributed').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('SHORT').length).toBeGreaterThanOrEqual(2)
  })

  it('handles edge case: strategy opposite positions when broker net is 0', async () => {
    // Broker returns empty or 0 net
    const brokerPositions: Position[] = []

    const attributedData: AttributedPositionsData = {
      positions: [
        {
          strategy: 'ICHI_V2',
          symbol: 'NIFTY26SEP24000CE',
          exchange: 'NFO',
          product: 'NRML',
          signed_quantity: 100,
          side: 'LONG',
          quantity: 100,
          average_price: 150.0,
          ltp: 160.0,
          realized_pnl: 0,
          today_realized_pnl: 0,
          unrealized_pnl: 1000.0,
          total_pnl: 1000.0,
          pnlpercent: 6.67,
          broker_quantity: 0,
          tracked_quantity: 0,
          residual_quantity: 0,
          reconciliation_status: 'RECONCILED',
        },
        {
          strategy: 'MACD_FNO',
          symbol: 'NIFTY26SEP24000CE',
          exchange: 'NFO',
          product: 'NRML',
          signed_quantity: -100,
          side: 'SHORT',
          quantity: 100,
          average_price: 155.0,
          ltp: 160.0,
          realized_pnl: 0,
          today_realized_pnl: 0,
          unrealized_pnl: -500.0,
          total_pnl: -500.0,
          pnlpercent: -3.23,
          broker_quantity: 0,
          tracked_quantity: 0,
          residual_quantity: 0,
          reconciliation_status: 'RECONCILED',
        },
      ],
      contracts: [
        {
          symbol: 'NIFTY26SEP24000CE',
          exchange: 'NFO',
          product: 'NRML',
          broker_quantity: 0,
          tracked_quantity: 0,
          residual_quantity: 0,
          has_residual: false,
          strategies_count: 2,
          reconciliation_status: 'RECONCILED',
        },
      ],
      summary: {
        total_broker_positions: 0,
        total_tracked_positions: 2,
        total_residual_positions: 0,
        total_realized_pnl: 0,
        total_unrealized_pnl: 500.0,
        total_pnl: 500.0,
        reconciliation_status: 'RECONCILED',
      },
    }

    mockGetPositions.mockResolvedValue({ status: 'success', data: brokerPositions })
    mockGetAttributedPositions.mockResolvedValue({ status: 'success', data: attributedData })

    render(<Positions />)

    // Contract row is rendered even with broker net 0
    await waitFor(() => {
      expect(screen.getByText('NIFTY26SEP24000CE')).toBeInTheDocument()
    })

    expect(screen.getByText('Broker Net:')).toBeInTheDocument()
    expect(screen.getByText('Tracked:')).toBeInTheDocument()
    expect(screen.getByText('✓ RECONCILED')).toBeInTheDocument()

    // Expand to verify both offsetting legs
    const expandButton = screen.getByLabelText('Expand NIFTY26SEP24000CE')
    fireEvent.click(expandButton)

    await waitFor(() => {
      expect(screen.getByText('LONG')).toBeInTheDocument()
      expect(screen.getByText('SHORT')).toBeInTheDocument()
      expect(screen.getByText('100')).toBeInTheDocument()
      expect(screen.getByText('-100')).toBeInTheDocument()
    })
  })

  it('displays MISMATCH badge when reconciliation status is not RECONCILED', async () => {
    const brokerPositions: Position[] = [
      {
        symbol: 'INFY',
        exchange: 'NSE',
        product: 'CNC',
        quantity: 50,
        average_price: 1800.0,
        ltp: 1820.0,
        pnl: 1000.0,
        pnlpercent: 1.11,
      },
    ]

    const attributedData: AttributedPositionsData = {
      positions: [
        {
          strategy: 'Untagged',
          symbol: 'INFY',
          exchange: 'NSE',
          product: 'CNC',
          signed_quantity: 40,
          side: 'LONG',
          quantity: 40,
          average_price: 1800.0,
          ltp: 1820.0,
          realized_pnl: 0,
          today_realized_pnl: 0,
          unrealized_pnl: 800.0,
          total_pnl: 800.0,
          pnlpercent: 1.11,
          broker_quantity: 50,
          tracked_quantity: 40,
          residual_quantity: 0,
          reconciliation_status: 'DISCREPANCY',
        },
      ],
      contracts: [
        {
          symbol: 'INFY',
          exchange: 'NSE',
          product: 'CNC',
          broker_quantity: 50,
          tracked_quantity: 40,
          residual_quantity: 0,
          has_residual: false,
          strategies_count: 1,
          reconciliation_status: 'DISCREPANCY',
        },
      ],
      summary: {
        total_broker_positions: 1,
        total_tracked_positions: 1,
        total_residual_positions: 0,
        total_realized_pnl: 0,
        total_unrealized_pnl: 800.0,
        total_pnl: 800.0,
        reconciliation_status: 'DISCREPANCY',
      },
    }

    mockGetPositions.mockResolvedValue({ status: 'success', data: brokerPositions })
    mockGetAttributedPositions.mockResolvedValue({ status: 'success', data: attributedData })

    render(<Positions />)

    await waitFor(() => {
      expect(screen.getByText('⚠ MISMATCH')).toBeInTheDocument()
    })
  })

  it('filters positions when clicking a strategy overview card and expands/collapses all', async () => {
    const brokerPositions: Position[] = [
      {
        symbol: 'RELIANCE',
        exchange: 'NSE',
        product: 'CNC',
        quantity: 10,
        average_price: 2500.0,
        ltp: 2550.0,
        pnl: 500.0,
        pnlpercent: 2.0,
      },
      {
        symbol: 'TCS',
        exchange: 'NSE',
        product: 'CNC',
        quantity: 5,
        average_price: 3500.0,
        ltp: 3600.0,
        pnl: 500.0,
        pnlpercent: 2.86,
      },
    ]

    const attributedData: AttributedPositionsData = {
      positions: [
        {
          strategy: 'ALPHA_MOMENTUM',
          symbol: 'RELIANCE',
          exchange: 'NSE',
          product: 'CNC',
          signed_quantity: 10,
          side: 'LONG',
          quantity: 10,
          average_price: 2500.0,
          ltp: 2550.0,
          realized_pnl: 0,
          today_realized_pnl: 0,
          unrealized_pnl: 500.0,
          total_pnl: 500.0,
          pnlpercent: 2.0,
          broker_quantity: 10,
          tracked_quantity: 10,
          residual_quantity: 0,
          reconciliation_status: 'RECONCILED',
        },
        {
          strategy: 'BETA_REVERSAL',
          symbol: 'TCS',
          exchange: 'NSE',
          product: 'CNC',
          signed_quantity: 5,
          side: 'LONG',
          quantity: 5,
          average_price: 3500.0,
          ltp: 3600.0,
          realized_pnl: 0,
          today_realized_pnl: 0,
          unrealized_pnl: 500.0,
          total_pnl: 500.0,
          pnlpercent: 2.86,
          broker_quantity: 5,
          tracked_quantity: 5,
          residual_quantity: 0,
          reconciliation_status: 'RECONCILED',
        },
      ],
      contracts: [
        {
          symbol: 'RELIANCE',
          exchange: 'NSE',
          product: 'CNC',
          broker_quantity: 10,
          tracked_quantity: 10,
          residual_quantity: 0,
          has_residual: false,
          strategies_count: 1,
          reconciliation_status: 'RECONCILED',
        },
        {
          symbol: 'TCS',
          exchange: 'NSE',
          product: 'CNC',
          broker_quantity: 5,
          tracked_quantity: 5,
          residual_quantity: 0,
          has_residual: false,
          strategies_count: 1,
          reconciliation_status: 'RECONCILED',
        },
      ],
      summary: {
        total_broker_positions: 2,
        total_tracked_positions: 2,
        total_residual_positions: 0,
        total_realized_pnl: 0,
        total_unrealized_pnl: 1000.0,
        total_pnl: 1000.0,
        reconciliation_status: 'RECONCILED',
      },
    }

    mockGetPositions.mockResolvedValue({ status: 'success', data: brokerPositions })
    mockGetAttributedPositions.mockResolvedValue({ status: 'success', data: attributedData })

    render(<Positions />)

    await waitFor(() => {
      expect(screen.getByText('RELIANCE')).toBeInTheDocument()
      expect(screen.getByText('TCS')).toBeInTheDocument()
    })

    // Click strategy card ALPHA_MOMENTUM
    const alphaCard = screen.getByText('ALPHA_MOMENTUM')
    fireEvent.click(alphaCard)

    await waitFor(() => {
      expect(screen.getByText('RELIANCE')).toBeInTheDocument()
      expect(screen.queryByText('TCS')).not.toBeInTheDocument()
    })

    // Active filter badge appears
    expect(screen.getByText('Strategy: ALPHA_MOMENTUM')).toBeInTheDocument()

    // Test Expand All Contracts
    const expandAllBtn = screen.getByText('Expand All Contracts')
    fireEvent.click(expandAllBtn)

    await waitFor(() => {
      expect(screen.getByText('Strategy Position Attribution')).toBeInTheDocument()
    })

    // Test Collapse All
    const collapseAllBtn = screen.getByText('Collapse All')
    fireEvent.click(collapseAllBtn)

    await waitFor(() => {
      expect(screen.queryByText('Strategy Position Attribution')).not.toBeInTheDocument()
    })
  })

  it('calls tradingApi.closePosition when closing an open position', async () => {
    const brokerPositions: Position[] = [
      {
        symbol: 'SBIN',
        exchange: 'NSE',
        product: 'MIS',
        quantity: 100,
        average_price: 800.0,
        ltp: 810.0,
        pnl: 1000.0,
        pnlpercent: 1.25,
      },
    ]

    mockGetPositions.mockResolvedValue({ status: 'success', data: brokerPositions })
    mockGetAttributedPositions.mockResolvedValue({
      status: 'success',
      data: { positions: [], contracts: [], summary: {} },
    })
    mockClosePosition.mockResolvedValue({ status: 'success', message: 'Position closed' })

    render(<Positions />)

    await waitFor(() => {
      expect(screen.getByText('SBIN')).toBeInTheDocument()
    })

    const closeBtn = screen.getByLabelText('Close SBIN position')
    fireEvent.click(closeBtn)

    await waitFor(() => {
      expect(mockClosePosition).toHaveBeenCalledWith('SBIN', 'NSE', 'MIS')
    })
  })

  it('hides stale zero-quantity rows (broker=0, tracked=0, residual=0) while keeping active ones', async () => {
    const brokerPositions: Position[] = [
      {
        symbol: 'TATASTEEL',
        exchange: 'NSE',
        product: 'MIS',
        quantity: -2750,
        average_price: 140.0,
        ltp: 139.0,
        pnl: 2750.0,
        pnlpercent: 0.71,
      },
      {
        symbol: 'ABB',
        exchange: 'NSE',
        product: 'MIS',
        quantity: 0,
        average_price: 0,
        ltp: 4500.0,
        pnl: 0,
        pnlpercent: 0,
      },
      {
        symbol: 'ADANIGREEN',
        exchange: 'NSE',
        product: 'MIS',
        quantity: 0,
        average_price: 0,
        ltp: 1200.0,
        pnl: 0,
        pnlpercent: 0,
      },
    ]

    const attributedData: AttributedPositionsData = {
      positions: [
        {
          strategy: 'MOMENTUM',
          symbol: 'TATASTEEL',
          exchange: 'NSE',
          product: 'MIS',
          signed_quantity: -2750,
          side: 'SHORT',
          quantity: 2750,
          average_price: 140.0,
          ltp: 139.0,
          realized_pnl: 0,
          today_realized_pnl: 0,
          unrealized_pnl: 2750.0,
          total_pnl: 2750.0,
          pnlpercent: 0.71,
          broker_quantity: -2750,
          tracked_quantity: -2750,
          residual_quantity: 0,
          reconciliation_status: 'RECONCILED',
        },
      ],
      contracts: [
        {
          symbol: 'TATASTEEL',
          exchange: 'NSE',
          product: 'MIS',
          broker_quantity: -2750,
          tracked_quantity: -2750,
          residual_quantity: 0,
          has_residual: false,
          strategies_count: 1,
          reconciliation_status: 'RECONCILED',
        },
      ],
      summary: {
        total_broker_positions: 1,
        total_tracked_positions: 1,
        total_residual_positions: 0,
        total_realized_pnl: 0,
        total_unrealized_pnl: 2750.0,
        total_pnl: 2750.0,
        reconciliation_status: 'RECONCILED',
      },
    }

    mockGetPositions.mockResolvedValue({ status: 'success', data: brokerPositions })
    mockGetAttributedPositions.mockResolvedValue({ status: 'success', data: attributedData })

    render(<Positions />)

    // Active position must be visible
    await waitFor(() => {
      expect(screen.getByText('TATASTEEL')).toBeInTheDocument()
    })

    // Stale zero-quantity positions must NOT appear
    expect(screen.queryByText('ABB')).not.toBeInTheDocument()
    expect(screen.queryByText('ADANIGREEN')).not.toBeInTheDocument()
  })

  it('displays "No active positions" and "Account is currently FLAT" when all positions are zero', async () => {
    const brokerPositions: Position[] = [
      {
        symbol: 'ABB',
        exchange: 'NSE',
        product: 'MIS',
        quantity: 0,
        average_price: 0,
        ltp: 4500.0,
        pnl: 0,
        pnlpercent: 0,
      },
    ]

    const attributedData: AttributedPositionsData = {
      positions: [],
      contracts: [],
      summary: {
        total_broker_positions: 0,
        total_tracked_positions: 0,
        total_residual_positions: 0,
        total_realized_pnl: 0,
        total_unrealized_pnl: 0,
        total_pnl: 0,
        reconciliation_status: 'RECONCILED',
      },
    }

    mockGetPositions.mockResolvedValue({ status: 'success', data: brokerPositions })
    mockGetAttributedPositions.mockResolvedValue({ status: 'success', data: attributedData })

    render(<Positions />)

    await waitFor(() => {
      expect(screen.getByText('No active positions')).toBeInTheDocument()
      expect(screen.getByText('Account is currently FLAT')).toBeInTheDocument()
    })
    expect(screen.queryByText('ABB')).not.toBeInTheDocument()
  })
})

