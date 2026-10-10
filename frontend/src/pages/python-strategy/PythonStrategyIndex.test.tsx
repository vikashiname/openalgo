import { fireEvent, render, screen, waitFor } from '@/test/test-utils'
import React from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { MasterContractStatus, PythonStrategy } from '@/types/python-strategy'

// Mock react-router useNavigate
const mockNavigate = vi.fn()
vi.mock('react-router', async () => {
  const actual = await vi.importActual('react-router')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    Link: ({ children, to, ...props }: { children: React.ReactNode; to: string }) => (
      <a href={to} {...props}>
        {children}
      </a>
    ),
  }
})

// Mock toast
vi.mock('@/utils/toast', () => ({
  showToast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))

vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuItem: ({
    children,
    onClick,
    disabled,
    className,
  }: {
    children: React.ReactNode
    onClick?: () => void
    disabled?: boolean
    className?: string
  }) => (
    <button type="button" onClick={onClick} disabled={disabled} className={className}>
      {children}
    </button>
  ),
  DropdownMenuSeparator: () => <hr />,
}))

// Mock Select component for jsdom compatibility
const SelectContext = React.createContext<{
  value?: string
  onValueChange?: (val: string) => void
}>({})

vi.mock('@/components/ui/select', () => ({
  Select: ({
    value,
    onValueChange,
    children,
  }: {
    value?: string
    onValueChange?: (v: string) => void
    children: React.ReactNode
  }) => (
    <SelectContext.Provider value={{ value, onValueChange }}>
      <div data-testid="strategy-filter-select">{children}</div>
    </SelectContext.Provider>
  ),
  SelectTrigger: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <div className={className}>{children}</div>
  ),
  SelectValue: ({ placeholder }: { placeholder?: string }) => {
    const ctx = React.useContext(SelectContext)
    return <span>{ctx.value || placeholder}</span>
  },
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ value, children }: { value: string; children: React.ReactNode }) => {
    const ctx = React.useContext(SelectContext)
    return (
      <button
        type="button"
        role="option"
        aria-selected={ctx.value === value}
        data-value={value}
        onClick={() => ctx.onValueChange?.(value)}
      >
        {children}
      </button>
    )
  },
}))

const rest = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}))

vi.mock('@/api/client', () => ({
  webClient: rest,
  apiClient: { get: vi.fn(), post: vi.fn() },
  authClient: { post: vi.fn() },
  fetchCSRFToken: vi.fn(),
  default: { get: vi.fn(), post: vi.fn() },
}))

// Mock EventSource
class MockEventSource {
  onmessage: ((event: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  close = vi.fn()
}
// @ts-expect-error Mocking global EventSource
globalThis.EventSource = MockEventSource
if (typeof window !== 'undefined') {
  // @ts-expect-error Mocking window EventSource
  window.EventSource = MockEventSource
}

const sampleStrategies: PythonStrategy[] = [
  {
    id: 'strat-1',
    name: 'EMA Crossover',
    file_name: 'ema_crossover.py',
    status: 'running',
    is_running: true,
    is_scheduled: true,
    schedule_start_time: '09:15',
    schedule_stop_time: '15:30',
    schedule_days: ['mon', 'tue', 'wed', 'thu', 'fri'],
    exchange: 'NSE',
    last_started: '2026-10-08T09:15:00',
    last_stopped: null,
    error_message: null,
    created_at: '2026-10-01T00:00:00',
    updated_at: '2026-10-08T09:15:00',
  },
  {
    id: 'strat-2',
    name: 'Supertrend Scalper',
    file_name: 'supertrend_scalper.py',
    status: 'scheduled',
    is_running: false,
    is_scheduled: true,
    schedule_start_time: '09:30',
    schedule_stop_time: '15:15',
    schedule_days: ['mon', 'tue', 'wed', 'thu', 'fri'],
    exchange: 'NFO',
    last_started: null,
    last_stopped: '2026-10-07T15:15:00',
    error_message: null,
    created_at: '2026-10-02T00:00:00',
    updated_at: '2026-10-07T15:15:00',
  },
  {
    id: 'strat-3',
    name: 'MACD Momentum',
    file_name: 'macd_momentum.py',
    status: 'stopped',
    is_running: false,
    is_scheduled: false,
    schedule_start_time: '09:15',
    schedule_stop_time: '15:30',
    schedule_days: ['mon', 'tue', 'wed', 'thu', 'fri'],
    exchange: 'MCX',
    last_started: '2026-10-05T09:15:00',
    last_stopped: '2026-10-05T15:30:00',
    error_message: null,
    created_at: '2026-10-03T00:00:00',
    updated_at: '2026-10-05T15:30:00',
  },
  {
    id: 'strat-4',
    name: 'Breakout Hunter',
    file_name: 'breakout_hunter.py',
    status: 'error',
    is_running: false,
    is_scheduled: false,
    schedule_start_time: '09:15',
    schedule_stop_time: '15:30',
    schedule_days: ['mon', 'tue', 'wed', 'thu', 'fri'],
    exchange: 'BSE',
    last_started: null,
    last_stopped: null,
    error_message: 'SyntaxError: invalid syntax',
    created_at: '2026-10-04T00:00:00',
    updated_at: '2026-10-04T00:00:00',
  },
]

const mockMasterStatus: MasterContractStatus = {
  ready: true,
  last_updated: '2026-10-08T08:00:00',
  message: 'Master contracts ready',
}

import PythonStrategyIndex from './PythonStrategyIndex'

describe('PythonStrategyIndex - Strategy Filter UI', () => {
  beforeEach(() => {
    rest.get.mockReset()
    rest.post.mockReset()
    rest.patch.mockReset()
    rest.delete.mockReset()

    rest.get.mockImplementation((url: string) => {
      if (url === '/python/api/strategies') {
        return Promise.resolve({ data: { strategies: sampleStrategies } })
      }
      if (url === '/python/status') {
        return Promise.resolve({ data: mockMasterStatus })
      }
      return Promise.reject(new Error(`Unexpected GET ${url}`))
    })
  })

  it('renders all strategy cards and the Strategy Filter dropdown with "All Strategies" as default', async () => {
    render(<PythonStrategyIndex />)

    // Wait for strategies to load - each strategy appears in the dropdown option and the card title
    await waitFor(() => {
      expect(screen.getAllByText('EMA Crossover')).toHaveLength(2)
      expect(screen.getAllByText('Supertrend Scalper')).toHaveLength(2)
      expect(screen.getAllByText('MACD Momentum')).toHaveLength(2)
      expect(screen.getAllByText('Breakout Hunter')).toHaveLength(2)
    })

    // Verify Strategy Filter dropdown exists with "All Strategies"
    expect(screen.getByText('All Strategies')).toBeInTheDocument()
  })

  it('includes strategies whether they are Running, Scheduled, Stopped, or in Error', async () => {
    render(<PythonStrategyIndex />)

    await waitFor(() => {
      // Running
      expect(screen.getAllByText('EMA Crossover')).toHaveLength(2)
      // Scheduled
      expect(screen.getAllByText('Supertrend Scalper')).toHaveLength(2)
      // Stopped
      expect(screen.getAllByText('MACD Momentum')).toHaveLength(2)
      // Error
      expect(screen.getAllByText('Breakout Hunter')).toHaveLength(2)
    })

    // Dropdown contains all strategies
    expect(screen.getByRole('option', { name: 'All Strategies' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'EMA Crossover' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Supertrend Scalper' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'MACD Momentum' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Breakout Hunter' })).toBeInTheDocument()
  })

  it('filters displayed cards when a strategy is selected from the dropdown', async () => {
    render(<PythonStrategyIndex />)

    await waitFor(() => {
      expect(screen.getAllByText('EMA Crossover')).toHaveLength(2)
    })

    // Select Supertrend Scalper
    fireEvent.click(screen.getByRole('option', { name: 'Supertrend Scalper' }))

    // Now only Supertrend Scalper card + dropdown item should exist (2 items), others only in dropdown (1 item)
    await waitFor(() => {
      expect(screen.getAllByText('Supertrend Scalper')).toHaveLength(2)
      expect(screen.getAllByText('EMA Crossover')).toHaveLength(1)
      expect(screen.getAllByText('MACD Momentum')).toHaveLength(1)
      expect(screen.getAllByText('Breakout Hunter')).toHaveLength(1)
    })

    // Select All Strategies again
    fireEvent.click(screen.getByRole('option', { name: 'All Strategies' }))

    // All cards should be visible again (2 items each: 1 in dropdown, 1 in card)
    await waitFor(() => {
      expect(screen.getAllByText('EMA Crossover')).toHaveLength(2)
      expect(screen.getAllByText('Supertrend Scalper')).toHaveLength(2)
      expect(screen.getAllByText('MACD Momentum')).toHaveLength(2)
      expect(screen.getAllByText('Breakout Hunter')).toHaveLength(2)
    })
  })

  it('shows empty state when no strategies are available', async () => {
    rest.get.mockImplementation((url: string) => {
      if (url === '/python/api/strategies') {
        return Promise.resolve({ data: { strategies: [] } })
      }
      if (url === '/python/status') {
        return Promise.resolve({ data: mockMasterStatus })
      }
      return Promise.reject(new Error(`Unexpected GET ${url}`))
    })

    render(<PythonStrategyIndex />)

    await waitFor(() => {
      expect(screen.getByText('No Python Strategies')).toBeInTheDocument()
    })

    // Dropdown should not be rendered when there are no strategies
    expect(screen.queryByTestId('strategy-filter-select')).not.toBeInTheDocument()
  })

  it('automatically displays newly added strategies in dropdown and cards from single data source', async () => {
    const dynamicStrategies: PythonStrategy[] = [
      ...sampleStrategies,
      {
        id: 'strat-5-custom',
        name: 'Custom RSI Strategy',
        file_name: 'custom_rsi.py',
        status: 'stopped',
        is_running: false,
        is_scheduled: false,
        schedule_start_time: '09:15',
        schedule_stop_time: '15:30',
        schedule_days: ['mon', 'tue', 'wed', 'thu', 'fri'],
        exchange: 'NSE',
        last_started: null,
        last_stopped: null,
        error_message: null,
        created_at: '2026-10-08T12:00:00',
        updated_at: '2026-10-08T12:00:00',
      },
    ]

    rest.get.mockImplementation((url: string) => {
      if (url === '/python/api/strategies') {
        return Promise.resolve({ data: { strategies: dynamicStrategies } })
      }
      if (url === '/python/status') {
        return Promise.resolve({ data: mockMasterStatus })
      }
      return Promise.reject(new Error(`Unexpected GET ${url}`))
    })

    render(<PythonStrategyIndex />)

    await waitFor(() => {
      expect(screen.getAllByText('Custom RSI Strategy')).toHaveLength(2)
      expect(screen.getByRole('option', { name: 'Custom RSI Strategy' })).toBeInTheDocument()
    })
  })

  it('resets selectedStrategy to "all" if the currently selected strategy is deleted', async () => {
    rest.post.mockImplementation((url: string) => {
      if (url === '/python/delete/strat-3') {
        return Promise.resolve({ data: { status: 'success', message: 'Strategy deleted' } })
      }
      return Promise.reject(new Error(`Unexpected POST ${url}`))
    })

    render(<PythonStrategyIndex />)

    await waitFor(() => {
      expect(screen.getAllByText('MACD Momentum')).toHaveLength(2)
    })

    // Select MACD Momentum
    fireEvent.click(screen.getByRole('option', { name: 'MACD Momentum' }))

    await waitFor(() => {
      expect(screen.getAllByText('MACD Momentum')).toHaveLength(2)
      expect(screen.getAllByText('EMA Crossover')).toHaveLength(1)
    })

    // Click actions menu and trigger delete
    const actionMenuBtn = screen.getByRole('button', { name: 'Strategy actions menu' })
    fireEvent.click(actionMenuBtn)

    const deleteMenuItem = screen.getByText('Delete')
    fireEvent.click(deleteMenuItem)

    // Confirm delete in dialog
    const confirmBtn = screen.getByRole('button', { name: 'Delete Strategy' })
    fireEvent.click(confirmBtn)

    // After delete, filter resets to 'all' and remaining cards are visible
    await waitFor(() => {
      expect(screen.queryByText('MACD Momentum')).not.toBeInTheDocument()
      expect(screen.getAllByText('EMA Crossover')).toHaveLength(2)
      expect(screen.getAllByText('Supertrend Scalper')).toHaveLength(2)
      expect(screen.getAllByText('Breakout Hunter')).toHaveLength(2)
    })
  })
})
