import {
  AlertTriangle,
  ArrowUpDown,
  ChartCandlestick,
  ChevronDown,
  ChevronRight,
  Download,
  Layers,
  Loader2,
  Pause,
  Radio,
  RefreshCw,
  Settings2,
  TrendingDown,
  TrendingUp,
  X,
} from 'lucide-react'
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { tradingApi } from '@/api/trading'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { EmptyState } from '@/components/ui/empty-state'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useLivePrice } from '@/hooks/useLivePrice'
import { useOrderEventRefresh } from '@/hooks/useOrderEventRefresh'
import { usePageVisibility } from '@/hooks/usePageVisibility'
import { useSupportedExchanges } from '@/hooks/useSupportedExchanges'
import { cn, makeFormatCurrency, sanitizeCSV } from '@/lib/utils'
import { useAuthStore } from '@/stores/authStore'
import { onModeChange } from '@/stores/themeStore'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import type {
  AttributedPositionsData,
  ClosedPosition,
  ContractReconciliation,
  Position,
  StrategyPositionItem,
} from '@/types/trading'
import { showToast } from '@/utils/toast'

const STORAGE_KEY = 'openalgo_positions_prefs'

export const AUTHORITATIVE_STRATEGIES = ['Macdfno', 'Emacrossopen'] as const

const DISALLOWED_TAGS = new Set([
  'ui exit position',
  'ui_exit_position',
  'ui exit',
  'manual / unattributed',
  'manual_/_unattributed',
  'manual',
  'unattributed',
  'untagged',
  'unknown',
  'target_exit',
  'sl_exit',
  'stoploss_exit',
  'squareoff',
  'square_off',
  'exit',
])

export function normalizeStrategy(name?: string | null): string | null {
  if (!name) return null
  const cleaned = name.trim()
  const lower = cleaned.toLowerCase()
  if (DISALLOWED_TAGS.has(lower) || DISALLOWED_TAGS.has(lower.replace(/-/g, '_'))) {
    return null
  }
  if (lower === 'macdfno' || lower === 'macd_fno_v1' || lower === 'macdfno_v1') {
    return 'Macdfno'
  }
  if (
    lower === 'emacrossopen' ||
    lower === 'emacross_fno_paper' ||
    lower === 'emacross_open'
  ) {
    return 'Emacrossopen'
  }
  return cleaned
}

type GroupingType = 'none' | 'underlying' | 'underlying_expiry'
type SortColumn = 0 | 3 | 4 | 6 | 7 | null
type SortDirection = 'asc' | 'desc'

interface FilterState {
  product: string[]
  direction: string[]
  exchange: string[]
}

interface Preferences {
  grouping: GroupingType
  filters: FilterState
  strategy?: string
}

function getContractKey(symbol: string, exchange: string, product: string): string {
  return `${(symbol || '').trim().toUpperCase()}-${(exchange || '').trim().toUpperCase()}-${(product || '').trim().toUpperCase()}`
}

function parseSymbol(symbol: string, exchange: string) {
  if (exchange === 'NSE' || exchange === 'BSE') {
    return { underlying: symbol, expiry: null, strike: null, optionType: null }
  }

  const futMatch = symbol.match(/^(.+?)(\d{1,2}[A-Z]{3}\d{2})FUT$/i)
  if (futMatch) {
    return { underlying: futMatch[1], expiry: futMatch[2], strike: null, optionType: 'FUT' }
  }

  const optMatch = symbol.match(/^(.+?)(\d{1,2}[A-Z]{3}\d{2})(\d+\.?\d*)(CE|PE)$/i)
  if (optMatch) {
    return {
      underlying: optMatch[1],
      expiry: optMatch[2],
      strike: optMatch[3],
      optionType: optMatch[4],
    }
  }

  return { underlying: symbol, expiry: null, strike: null, optionType: null }
}

function calculatePnlPercent(position: Position): number {
  const avgPrice = Number(position.average_price) || 0
  const qty = Number(position.quantity) || 0
  const pnl = Number(position.pnl) || 0

  // Use API-provided pnlpercent if available
  if (position.pnlpercent !== undefined && position.pnlpercent !== null) {
    return Number(position.pnlpercent) || 0
  }

  if (avgPrice === 0) return 0

  // For open positions with quantity, calculate based on investment
  if (qty !== 0) {
    const investment = Math.abs(avgPrice * qty)
    return investment > 0 ? (pnl / investment) * 100 : 0
  }

  // For closed positions (qty=0), return 0% like Zerodha
  // We cannot reliably calculate P&L% without knowing the original quantity
  // The P&L amount is still shown correctly from the API
  return 0
}

const EXCHANGE_COLORS: Record<string, string> = {
  NSE: 'bg-cyan-500/20 text-cyan-600 border-cyan-500/30',
  BSE: 'bg-slate-500/20 text-slate-600 border-slate-500/30',
  NFO: 'bg-purple-500/20 text-purple-600 border-purple-500/30',
  BFO: 'bg-amber-500/20 text-amber-600 border-amber-500/30',
  MCX: 'bg-blue-500/20 text-blue-600 border-blue-500/30',
  NCO: 'bg-emerald-500/20 text-emerald-600 border-emerald-500/30',
  CDS: 'bg-teal-500/20 text-teal-600 border-teal-500/30',
  NSE_INDEX: 'bg-cyan-500/20 text-cyan-600 border-cyan-500/30',
  BSE_INDEX: 'bg-slate-500/20 text-slate-600 border-slate-500/30',
  GLOBAL_INDEX: 'bg-indigo-500/20 text-indigo-600 border-indigo-500/30',
}

const PRODUCT_COLORS: Record<string, string> = {
  CNC: 'bg-purple-500/20 text-purple-600 border-purple-500/30',
  MIS: 'bg-cyan-500/20 text-cyan-600 border-cyan-500/30',
  NRML: 'bg-slate-500/20 text-slate-600 border-slate-500/30',
}

function withTimeout<T>(promise: Promise<T>, ms: number, fallbackMsg: string): Promise<T> {
  return Promise.race([
    promise,
    new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error(fallbackMsg)), ms)
    ),
  ])
}

export default function Positions() {
  const { apiKey, user } = useAuthStore()
  const { isCrypto } = useSupportedExchanges()
  const formatCurrency = useMemo(() => makeFormatCurrency(user?.broker), [user?.broker])
  const [positions, setPositions] = useState<Position[]>([])
  const [attributedData, setAttributedData] = useState<AttributedPositionsData | null>(null)
  const [expandedContracts, setExpandedContracts] = useState<Set<string>>(new Set())
  const [selectedStrategy, setSelectedStrategy] = useState<string>('all')
  const [positionsTab, setPositionsTab] = useState<'active' | 'closed'>('active')

  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showStaleWarning, setShowStaleWarning] = useState(false)
  const isFetchingRef = useRef<boolean>(false)

  // Page visibility tracking for resource optimization
  const { isVisible, wasHidden, timeSinceHidden } = usePageVisibility()
  const lastFetchRef = useRef<number>(Date.now())

  // Filter and grouping state
  const [grouping, setGrouping] = useState<GroupingType>('none')
  const [filters, setFilters] = useState<FilterState>({
    product: [],
    direction: [],
    exchange: [],
  })
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set())
  const [sortColumn, setSortColumn] = useState<SortColumn>(null)
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc')
  const [settingsOpen, setSettingsOpen] = useState(false)

  // Centralized real-time price hook with WebSocket + MultiQuotes fallback
  // Automatically pauses when tab is hidden
  const {
    data: enhancedPositions,
    isLive,
    isPaused,
  } = useLivePrice(positions, {
    enabled: positions.length > 0,
    useMultiQuotesFallback: true,
    staleThreshold: 5000,
    multiQuotesRefreshInterval: 30000,
    pauseWhenHidden: true,
  })

  // Load preferences from localStorage
  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (saved) {
        const prefs: Preferences = JSON.parse(saved)
        if (prefs.grouping) setGrouping(prefs.grouping)
        if (prefs.strategy) {
          const norm = normalizeStrategy(prefs.strategy)
          setSelectedStrategy(norm || 'all')
        }
        if (prefs.filters)
          setFilters({
            product: prefs.filters.product || [],
            direction: prefs.filters.direction || [],
            exchange: prefs.filters.exchange || [],
          })
      }
    } catch (_e) {}
  }, [])

  // Save preferences to localStorage
  const savePreferences = useCallback(() => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ grouping, filters, strategy: selectedStrategy })
    )
  }, [grouping, filters, selectedStrategy])

  useEffect(() => {
    savePreferences()
  }, [savePreferences])

  const fetchPositions = useCallback(
    async (showRefresh = false) => {
      if (!apiKey) {
        setIsLoading(false)
        return
      }

      if (isFetchingRef.current && !showRefresh) {
        return
      }
      isFetchingRef.current = true

      if (showRefresh) setIsRefreshing(true)

      try {
        const [posResp, attrResp] = await Promise.allSettled([
          withTimeout(tradingApi.getPositions(apiKey), 10000, 'Position book request timed out'),
          withTimeout(
            tradingApi.getAttributedPositions(apiKey, undefined, true),
            10000,
            'Attributed positions request timed out'
          ),
        ])

        let basePositions: Position[] = []
        let hasValidPosData = false
        let posError: string | null = null

        if (
          posResp.status === 'fulfilled' &&
          posResp.value.status === 'success' &&
          Array.isArray(posResp.value.data)
        ) {
          basePositions = posResp.value.data
          hasValidPosData = true
        } else if (posResp.status === 'fulfilled') {
          posError = posResp.value.message || 'Failed to fetch positions'
        } else {
          const reason = (posResp as PromiseRejectedResult).reason
          posError =
            reason?.response?.data?.message || reason?.message || 'Failed to fetch positions'
        }

        if (
          attrResp.status === 'fulfilled' &&
          attrResp.value.status === 'success' &&
          attrResp.value.data
        ) {
          const attrData = attrResp.value.data
          setAttributedData(attrData)
          setError(null)

          // Build local map of reconciliation data from attrData
          const recMap = new Map<string, ContractReconciliation>()
          for (const c of attrData.contracts || []) {
            recMap.set(getContractKey(c.symbol, c.exchange, c.product), c)
          }

          // Handle Edge Case 1: Strategy opposite positions or contracts present in attribution
          // where broker_quantity === 0 (or not returned by broker in positionbook).
          // If a contract exists in attribution but not in basePositions, inject a synthetic position
          // Handle Edge Case: Strategy contracts present in attribution where broker_quantity != 0
          // but not yet in basePositions. Flat broker contracts are NEVER injected into Active.
          const existingKeys = new Set(
            basePositions.map((p) => getContractKey(p.symbol, p.exchange, p.product))
          )

          const syntheticPositions: Position[] = []
          for (const contract of attrData.contracts || []) {
            if (Math.abs(contract.broker_quantity || 0) <= 1e-9) continue
            const key = getContractKey(contract.symbol, contract.exchange, contract.product)
            if (!existingKeys.has(key)) {
              const legs = (attrData.positions || []).filter(
                (p) => getContractKey(p.symbol, p.exchange, p.product) === key
              )
              const sampleLeg = legs[0]
              syntheticPositions.push({
                symbol: contract.symbol,
                exchange: contract.exchange,
                product: contract.product as 'MIS' | 'NRML' | 'CNC',
                quantity: contract.broker_quantity,
                average_price: sampleLeg ? sampleLeg.average_price : 0,
                ltp: sampleLeg ? sampleLeg.ltp : 0,
                pnl: 0,
                pnlpercent: 0,
              })
              existingKeys.add(key)
            }
          }

          if (syntheticPositions.length > 0) {
            basePositions = [...basePositions, ...syntheticPositions]
          }

          // Authoritative Active Position Rule:
          // A position is considered ACTIVE only when broker net quantity is non-zero (abs(quantity) > 1e-9).
          // Stale tracking or residual quantity must NEVER keep a flat broker position in Active.
          basePositions = basePositions.filter((p) => Math.abs(p.quantity || 0) > 1e-9)

          setPositions(basePositions)
        } else if (hasValidPosData) {
          // Attribution data not available, but base positions succeeded:
          // Filter base positions by non-zero broker quantity
          basePositions = basePositions.filter((p) => Math.abs(p.quantity || 0) > 1e-9)
          setPositions(basePositions)
          setError(null)
        } else {
          // Both failed
          const attrReason =
            attrResp.status === 'rejected' ? (attrResp as PromiseRejectedResult).reason : null
          const attrMsg =
            attrReason?.response?.data?.message ||
            attrReason?.message ||
            (attrResp.status === 'fulfilled' ? attrResp.value?.message : null)
          setError(attrMsg || posError || 'Failed to fetch positions')
        }
      } catch (err: unknown) {
        const msg = (err as { message?: string })?.message
        setError(msg || 'Failed to fetch positions')
      } finally {
        setIsLoading(false)
        setIsRefreshing(false)
        isFetchingRef.current = false
      }
    },
    [apiKey]
  )

  // Safety fallback: ensure isLoading cannot remain true indefinitely (max 12 seconds)
  useEffect(() => {
    if (!isLoading) return
    const timer = setTimeout(() => {
      setIsLoading(false)
    }, 12000)
    return () => clearTimeout(timer)
  }, [isLoading])

  // Initial fetch and visibility-aware polling
  // Pauses polling when tab is hidden to save resources
  useEffect(() => {
    // Don't poll when tab is hidden
    if (!isVisible) return

    fetchPositions()
    lastFetchRef.current = Date.now()
  }, [fetchPositions, isVisible])

  // Refresh on order events instead of polling
  useOrderEventRefresh(fetchPositions, {
    events: ['order_event', 'analyzer_update', 'close_position_event'],
  })

  // Refresh data when tab becomes visible after being hidden
  useEffect(() => {
    if (!wasHidden || !isVisible) return

    const timeSinceLastFetch = Date.now() - lastFetchRef.current

    // If hidden for more than 30 seconds, show stale warning and refresh
    if (timeSinceHidden > 30000 || timeSinceLastFetch > 30000) {
      setShowStaleWarning(true)
      fetchPositions()
      lastFetchRef.current = Date.now()
    }
  }, [wasHidden, isVisible, timeSinceHidden, fetchPositions])

  // Auto-dismiss stale data warning after 5 seconds
  useEffect(() => {
    if (!showStaleWarning) return
    const timeout = setTimeout(() => setShowStaleWarning(false), 5000)
    return () => clearTimeout(timeout)
  }, [showStaleWarning])

  // Listen for mode changes (live/analyze) and refresh data
  useEffect(() => {
    const unsubscribe = onModeChange(() => {
      fetchPositions()
    })
    return () => unsubscribe()
  }, [fetchPositions])

  // Lookup maps for fast contract reconciliation access
  const contractRecMap = useMemo(() => {
    const map = new Map<string, ContractReconciliation>()
    if (attributedData?.contracts) {
      for (const c of attributedData.contracts) {
        map.set(getContractKey(c.symbol, c.exchange, c.product), c)
      }
    }
    return map
  }, [attributedData])

  const contractLegsMap = useMemo(() => {
    const map = new Map<string, StrategyPositionItem[]>()
    if (attributedData?.positions) {
      for (const p of attributedData.positions) {
        const key = getContractKey(p.symbol, p.exchange, p.product)
        const list = map.get(key) || []
        list.push(p)
        map.set(key, list)
      }
    }
    return map
  }, [attributedData])

  // Available strategies for filtering (excludes disallowed/system tags)
  const availableStrategies = useMemo(() => {
    const set = new Set<string>()
    if (attributedData?.positions) {
      for (const p of attributedData.positions) {
        const canon = normalizeStrategy(p.strategy)
        if (canon) set.add(canon)
      }
    }
    if (attributedData?.closed_positions) {
      for (const cp of attributedData.closed_positions) {
        const canon = normalizeStrategy(cp.strategy)
        if (canon) set.add(canon)
      }
    }
    return Array.from(set).sort((a, b) => a.localeCompare(b))
  }, [attributedData])

  // Strategy summary statistics: strictly excludes disallowed tags like Manual / Unattributed & UI Exit Position
  const strategyStats = useMemo(() => {
    if (!attributedData?.positions && !attributedData?.closed_positions) return []

    const statsMap = new Map<
      string,
      {
        name: string
        count: number
        closedCount: number
        totalPnl: number
        unrealizedPnl: number
        realizedPnl: number
      }
    >()

    for (const pos of attributedData?.positions || []) {
      const canon = normalizeStrategy(pos.strategy)
      if (!canon) continue

      // Authoritative Rule: Strategy active count must only count broker-active contracts
      const parent = enhancedPositions.find(
        (ep) =>
          getContractKey(ep.symbol, ep.exchange, ep.product) ===
          getContractKey(pos.symbol, pos.exchange, pos.product)
      )
      const brokerQty = parent ? parent.quantity || 0 : pos.broker_quantity || 0
      if (Math.abs(brokerQty) <= 1e-9) continue

      let entry = statsMap.get(canon)
      if (!entry) {
        entry = { name: canon, count: 0, closedCount: 0, totalPnl: 0, unrealizedPnl: 0, realizedPnl: 0 }
        statsMap.set(canon, entry)
      }

      // Read parent contract's live LTP
      const ltp = parent?.ltp ?? pos.ltp

      let unrealized = pos.unrealized_pnl
      if (ltp !== undefined && ltp > 0 && Math.abs(pos.signed_quantity) > 1e-9) {
        unrealized = pos.signed_quantity * (ltp - pos.average_price)
      }
      const total = pos.realized_pnl + unrealized

      if (Math.abs(pos.signed_quantity) > 1e-9) {
        entry.count += 1
      }
      entry.realizedPnl += pos.realized_pnl
      entry.unrealizedPnl += unrealized
      entry.totalPnl += total
    }

    if (attributedData?.closed_positions) {
      for (const cp of attributedData.closed_positions) {
        const canon = normalizeStrategy(cp.strategy)
        if (!canon) continue

        let entry = statsMap.get(canon)
        if (!entry) {
          entry = {
            name: canon,
            count: 0,
            closedCount: 1,
            totalPnl: cp.realized_pnl,
            unrealizedPnl: 0,
            realizedPnl: cp.realized_pnl,
          }
          statsMap.set(canon, entry)
        } else {
          entry.closedCount += 1
          entry.realizedPnl += cp.realized_pnl
          entry.totalPnl += cp.realized_pnl
        }
      }
    }

    // Display a strategy card only when activeCount > 0 OR closedCount > 0
    return Array.from(statsMap.values())
      .filter((s) => s.count > 0 || s.closedCount > 0)
      .sort((a, b) => b.totalPnl - a.totalPnl)
  }, [attributedData, enhancedPositions])

  // Filtered closed positions based on selectedStrategy
  const filteredClosedPositions: ClosedPosition[] = useMemo(() => {
    const list = attributedData?.closed_positions || []
    if (selectedStrategy === 'all') return list
    return list.filter(
      (p) => (p.strategy || '').toLowerCase() === selectedStrategy.toLowerCase()
    )
  }, [attributedData, selectedStrategy])

  const totalClosedPnl = useMemo(() => {
    return filteredClosedPositions.reduce((sum, p) => sum + (p.realized_pnl || 0), 0)
  }, [filteredClosedPositions])

  // Get group key for a position
  const getGroupKey = useCallback(
    (pos: Position): string => {
      const exchange = pos.exchange
      const product = pos.product

      if (exchange === 'NSE' || exchange === 'BSE') {
        if (product === 'CNC') return 'Equity (Delivery)'
        if (product === 'MIS') return 'Equity (Intraday)'
      }

      const parsed = parseSymbol(pos.symbol, exchange)

      if (grouping === 'underlying') {
        return parsed.underlying
      } else if (grouping === 'underlying_expiry') {
        return parsed.expiry ? `${parsed.underlying} - ${parsed.expiry}` : parsed.underlying
      }

      return 'Other'
    },
    [grouping]
  )

  // Filter positions (use enhancedPositions for real-time LTP/PnL)
  const filteredPositions = useMemo(() => {
    return enhancedPositions.filter((pos) => {
      // Authoritative Active Position Rule:
      // A contract may appear in Active Positions ONLY when abs(broker_net_quantity) > 1e-9.
      // Stale tracking, residual quantity, or strategy counts must NEVER keep a flat broker position in Active.
      if (Math.abs(pos.quantity || 0) <= 1e-9) {
        return false
      }

      if (filters.product.length > 0 && !filters.product.includes(pos.product)) return false

      const qty = pos.quantity || 0
      if (filters.direction.length > 0) {
        const isLong = qty > 0
        const isShort = qty < 0
        if (filters.direction.includes('LONG') && !filters.direction.includes('SHORT') && !isLong)
          return false
        if (filters.direction.includes('SHORT') && !filters.direction.includes('LONG') && !isShort)
          return false
      }

      if (filters.exchange.length > 0 && !filters.exchange.includes(pos.exchange)) return false

      if (selectedStrategy !== 'all') {
        const key = getContractKey(pos.symbol, pos.exchange, pos.product)
        const legs = contractLegsMap.get(key) || []
        const hasStrategy = legs.some(
          (l) => l.strategy.toLowerCase() === selectedStrategy.toLowerCase()
        )
        if (!hasStrategy) return false
      }

      return true
    })
  }, [enhancedPositions, filters, selectedStrategy, contractRecMap, contractLegsMap])

  // Sort positions
  const sortedPositions = useMemo(() => {
    if (sortColumn === null) return filteredPositions

    return [...filteredPositions].sort((a, b) => {
      let aVal: string | number
      let bVal: string | number

      switch (sortColumn) {
        case 0:
          aVal = a.symbol
          bVal = b.symbol
          break
        case 3:
          aVal = a.quantity || 0
          bVal = b.quantity || 0
          break
        case 4:
          aVal = a.average_price || 0
          bVal = b.average_price || 0
          break
        case 6:
          aVal = a.pnl || 0
          bVal = b.pnl || 0
          break
        case 7:
          aVal = calculatePnlPercent(a)
          bVal = calculatePnlPercent(b)
          break
        default:
          return 0
      }

      if (typeof aVal === 'string') {
        return sortDirection === 'asc'
          ? aVal.localeCompare(bVal as string)
          : (bVal as string).localeCompare(aVal)
      }
      return sortDirection === 'asc'
        ? (aVal as number) - (bVal as number)
        : (bVal as number) - (aVal as number)
    })
  }, [filteredPositions, sortColumn, sortDirection])

  // Group positions
  const groupedPositions = useMemo(() => {
    if (grouping === 'none') {
      return { _all: sortedPositions }
    }

    const groups: Record<string, Position[]> = {}
    sortedPositions.forEach((pos) => {
      const groupKey = getGroupKey(pos)
      if (!groups[groupKey]) groups[groupKey] = []
      groups[groupKey].push(pos)
    })

    return groups
  }, [sortedPositions, grouping, getGroupKey])

  // Calculate stats
  const stats = useMemo(() => {
    const long = filteredPositions.filter((p) => (p.quantity || 0) > 0).length
    const short = filteredPositions.filter((p) => (p.quantity || 0) < 0).length
    // Only count positions with non-zero quantity as "open"
    const total = long + short
    const totalPnl = filteredPositions.reduce((sum, p) => sum + (p.pnl || 0), 0)
    return { total, long, short, totalPnl }
  }, [filteredPositions])

  const handleSort = (column: SortColumn) => {
    if (sortColumn === column) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc')
    } else {
      setSortColumn(column)
      setSortDirection('asc')
    }
  }

  const toggleFilter = (type: keyof FilterState, value: string) => {
    setFilters((prev) => {
      const arr = prev[type]
      const index = arr.indexOf(value)
      if (index > -1) {
        return { ...prev, [type]: arr.filter((v) => v !== value) }
      }
      return { ...prev, [type]: [...arr, value] }
    })
  }

  const clearFilters = () => {
    setFilters({ product: [], direction: [], exchange: [] })
    setSelectedStrategy('all')
    setGrouping('none')
    setCollapsedGroups(new Set())
  }

  const toggleGroup = (groupKey: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev)
      if (next.has(groupKey)) {
        next.delete(groupKey)
      } else {
        next.add(groupKey)
      }
      return next
    })
  }

  const toggleExpand = (contractKeyStr: string) => {
    setExpandedContracts((prev) => {
      const next = new Set(prev)
      if (next.has(contractKeyStr)) {
        next.delete(contractKeyStr)
      } else {
        next.add(contractKeyStr)
      }
      return next
    })
  }

  const expandAll = () => {
    const allKeys = new Set<string>()
    filteredPositions.forEach((pos) => {
      allKeys.add(getContractKey(pos.symbol, pos.exchange, pos.product))
    })
    setExpandedContracts(allKeys)
  }

  const collapseAll = () => {
    setExpandedContracts(new Set())
  }

  const hasActiveFilters =
    filters.product.length > 0 ||
    filters.direction.length > 0 ||
    filters.exchange.length > 0 ||
    selectedStrategy !== 'all' ||
    grouping !== 'none'

  const handleClosePosition = async (position: Position) => {
    try {
      const cKey = getContractKey(position.symbol, position.exchange, position.product)
      const legs = contractLegsMap.get(cKey) || []
      const activeLeg = legs.find((l) => Math.abs(l.signed_quantity) > 1e-9)
      const targetStrategy =
        selectedStrategy !== 'all'
          ? selectedStrategy
          : activeLeg
          ? activeLeg.strategy
          : undefined

      const response = targetStrategy
        ? await tradingApi.closePosition(
            position.symbol,
            position.exchange,
            position.product,
            targetStrategy
          )
        : await tradingApi.closePosition(
            position.symbol,
            position.exchange,
            position.product
          )
      if (response.status === 'success') {
        showToast.success(response.message || `Position closed for ${position.symbol}`, 'positions')
        fetchPositions(true)
      } else {
        showToast.error(response.message || 'Failed to close position', 'positions')
      }
    } catch (_err) {
      showToast.error('Failed to close position', 'positions')
    }
  }

  const handleCloseAllPositions = async () => {
    try {
      const response = await tradingApi.closeAllPositions()
      if (response.status === 'success') {
        // Toast handled by close_position_event socket
        fetchPositions(true)
      } else {
        showToast.error(response.message || 'Failed to close all positions', 'positions')
      }
    } catch (_err) {
      showToast.error('Failed to close all positions', 'positions')
    }
  }

  const exportToCSV = () => {
    if (positionsTab === 'closed') {
      if (filteredClosedPositions.length === 0) {
        showToast.error('No data to export', 'system')
        return
      }

      try {
        const headers = [
          'Strategy',
          'Symbol',
          'Exchange',
          'Product',
          'Direction',
          'Quantity',
          'Entry Avg',
          'Exit Avg',
          'Entry Time',
          'Exit Time',
          'Realized P&L',
          'Status',
        ]
        const rows = filteredClosedPositions.map((p) => [
          sanitizeCSV(p.strategy),
          sanitizeCSV(p.symbol),
          sanitizeCSV(p.exchange),
          sanitizeCSV(p.product),
          sanitizeCSV(p.direction),
          sanitizeCSV(p.quantity),
          sanitizeCSV(p.entry_average),
          sanitizeCSV(p.exit_average),
          sanitizeCSV(p.entry_time),
          sanitizeCSV(p.exit_time),
          sanitizeCSV(p.realized_pnl),
          sanitizeCSV(p.status),
        ])

        const csv = [headers, ...rows].map((row) => row.join(',')).join('\n')
        const blob = new Blob([csv], { type: 'text/csv' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        const filename = `closed_positions_${new Date().toISOString().split('T')[0]}.csv`
        a.download = filename
        a.click()
        URL.revokeObjectURL(url)
        showToast.success(`Downloaded ${filename}`, 'clipboard')
      } catch {
        showToast.error('Failed to export CSV', 'system')
      }
      return
    }

    if (filteredPositions.length === 0) {
      showToast.error('No data to export', 'system')
      return
    }

    try {
      const headers = [
        'Symbol',
        'Exchange',
        ...(isCrypto ? [] : ['Product']),
        'Quantity',
        'Avg Price',
        'LTP',
        'P&L',
        'P&L %',
      ]
      const rows = filteredPositions.map((p) => [
        sanitizeCSV(p.symbol),
        sanitizeCSV(p.exchange),
        ...(isCrypto ? [] : [sanitizeCSV(p.product)]),
        sanitizeCSV(p.quantity),
        sanitizeCSV(p.average_price),
        sanitizeCSV(p.ltp),
        sanitizeCSV(p.pnl),
        sanitizeCSV(calculatePnlPercent(p)),
      ])

      const csv = [headers, ...rows].map((row) => row.join(',')).join('\n')
      const blob = new Blob([csv], { type: 'text/csv' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const filename = `positions_${new Date().toISOString().split('T')[0]}.csv`
      a.download = filename
      a.click()
      // Revoke the object URL to free memory
      URL.revokeObjectURL(url)
      showToast.success(`Downloaded ${filename}`, 'clipboard')
    } catch {
      showToast.error('Failed to export CSV', 'system')
    }
  }

  const isProfit = (value: number) => value >= 0

  const FilterChip = ({
    type,
    value,
    label,
  }: {
    type: keyof FilterState
    value: string
    label: string
  }) => (
    <Button
      variant={filters[type].includes(value) ? 'default' : 'outline'}
      size="sm"
      className={cn(
        'rounded-full',
        filters[type].includes(value) && 'bg-pink-500 hover:bg-pink-600'
      )}
      onClick={() => toggleFilter(type, value)}
    >
      {label}
    </Button>
  )

  const SortableHeader = ({
    column,
    label,
    className,
  }: {
    column: SortColumn
    label: string
    className?: string
  }) => (
    <TableHead
      className={cn('cursor-pointer hover:bg-muted/50 select-none', className)}
      onClick={() => handleSort(column)}
    >
      <div
        className={cn(
          'flex items-center gap-1 w-full',
          className?.includes('text-right') && 'justify-end'
        )}
      >
        {label}
        <ArrowUpDown className="h-3 w-3 opacity-50" />
      </div>
    </TableHead>
  )

  // Calculate group stats
  const calculateGroupStats = (positions: Position[]) => {
    let totalPnl = 0
    let totalInvestment = 0

    positions.forEach((pos) => {
      totalPnl += pos.pnl || 0
      const avgPrice = pos.average_price || 0
      const qty = Math.abs(pos.quantity || 0)
      totalInvestment += avgPrice * qty
    })

    const pnlPercent = totalInvestment > 0 ? (totalPnl / totalInvestment) * 100 : 0
    return { totalPnl, pnlPercent, count: positions.length }
  }

  // Sort group keys
  const sortedGroupKeys = Object.keys(groupedPositions).sort((a, b) => {
    if (a.startsWith('Equity') && !b.startsWith('Equity')) return -1
    if (!a.startsWith('Equity') && b.startsWith('Equity')) return 1
    return a.localeCompare(b)
  })

  return (
    <div className="space-y-6">
      {/* Stale Data Warning */}
      {showStaleWarning && (
        <Alert variant="default" className="bg-amber-500/10 border-amber-500/30">
          <AlertTriangle className="h-4 w-4 text-amber-600" />
          <AlertDescription className="text-amber-700 dark:text-amber-400">
            Data is being refreshed after tab was inactive...
          </AlertDescription>
        </Alert>
      )}

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-bold tracking-tight">Positions</h1>
            {isPaused ? (
              <Badge
                variant="outline"
                className="bg-amber-500/10 text-amber-600 border-amber-500/30 gap-1"
              >
                <Pause className="h-3 w-3" />
                Paused
              </Badge>
            ) : isLive ? (
              <Badge
                variant="outline"
                className="bg-emerald-500/10 text-emerald-600 border-emerald-500/30 gap-1"
              >
                <Radio className="h-3 w-3 animate-pulse" />
                Live
              </Badge>
            ) : null}
          </div>
          <p className="text-muted-foreground">Monitor and manage your active trading positions</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {/* Strategy Selector */}
          {availableStrategies.length > 0 && (
            <div className="w-[170px]">
              <Select value={selectedStrategy} onValueChange={setSelectedStrategy}>
                <SelectTrigger size="sm" className="h-9 text-xs">
                  <SelectValue placeholder="All Strategies" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Strategies</SelectItem>
                  {availableStrategies.map((strat) => (
                    <SelectItem key={strat} value={strat}>
                      {strat}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {/* Settings Button */}
          <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
            <DialogTrigger asChild>
              <Button
                variant={hasActiveFilters ? 'default' : 'outline'}
                size="sm"
                className="relative"
              >
                <Settings2 className="h-4 w-4 mr-2" />
                Settings
                {hasActiveFilters && (
                  <span className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-red-500 rounded-full" />
                )}
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-md">
              <DialogHeader>
                <DialogTitle>Position Settings</DialogTitle>
                <DialogDescription>Configure grouping and filters</DialogDescription>
              </DialogHeader>

              <div className="space-y-6 py-4">
                {/* Grouping */}
                <div className="space-y-3">
                  <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Grouping
                  </Label>
                  <div className="space-y-2">
                    {[
                      { value: 'none', label: 'None' },
                      { value: 'underlying', label: 'Underlying' },
                      { value: 'underlying_expiry', label: 'Underlying & Expiry' },
                    ].map((opt) => (
                      <label
                        key={opt.value}
                        className={cn(
                          'flex items-center gap-3 cursor-pointer p-2 rounded hover:bg-muted',
                          grouping === opt.value && 'bg-pink-500/10 border border-pink-500/30'
                        )}
                      >
                        <input
                          type="radio"
                          name="grouping"
                          checked={grouping === opt.value}
                          onChange={() => {
                            setGrouping(opt.value as GroupingType)
                            setCollapsedGroups(new Set())
                          }}
                          className="accent-pink-500"
                        />
                        <span
                          className={cn(grouping === opt.value && 'text-pink-500 font-semibold')}
                        >
                          {opt.label}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>

                <div className="border-t" />

                {/* Strategy Filter in Settings */}
                {availableStrategies.length > 0 && (
                  <div className="space-y-3">
                    <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      Strategy Filter
                    </Label>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        variant={selectedStrategy === 'all' ? 'default' : 'outline'}
                        size="sm"
                        className={cn(
                          'rounded-full text-xs',
                          selectedStrategy === 'all' && 'bg-primary hover:bg-primary/90'
                        )}
                        onClick={() => setSelectedStrategy('all')}
                      >
                        All
                      </Button>
                      {availableStrategies.map((strat) => (
                        <Button
                          key={strat}
                          variant={selectedStrategy === strat ? 'default' : 'outline'}
                          size="sm"
                          className={cn(
                            'rounded-full text-xs',
                            selectedStrategy === strat && 'bg-primary hover:bg-primary/90'
                          )}
                          onClick={() => setSelectedStrategy(strat)}
                        >
                          {strat}
                        </Button>
                      ))}
                    </div>
                  </div>
                )}

                {/* Product Type */}
                {!isCrypto && (
                  <div className="space-y-3">
                    <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      Product Type
                    </Label>
                    <div className="flex flex-wrap gap-2">
                      <FilterChip type="product" value="CNC" label="CNC" />
                      <FilterChip type="product" value="MIS" label="MIS" />
                      <FilterChip type="product" value="NRML" label="NRML" />
                    </div>
                  </div>
                )}

                {/* Direction */}
                <div className="space-y-3">
                  <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Direction
                  </Label>
                  <div className="flex flex-wrap gap-2">
                    <FilterChip type="direction" value="LONG" label="Long" />
                    <FilterChip type="direction" value="SHORT" label="Short" />
                  </div>
                </div>

                {/* Exchange */}
                <div className="space-y-3">
                  <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Exchange
                  </Label>
                  <div className="flex flex-wrap gap-2">
                    <FilterChip type="exchange" value="NSE" label="NSE" />
                    <FilterChip type="exchange" value="BSE" label="BSE" />
                    <FilterChip type="exchange" value="NFO" label="NFO" />
                    <FilterChip type="exchange" value="BFO" label="BFO" />
                    <FilterChip type="exchange" value="MCX" label="MCX" />
                    <FilterChip type="exchange" value="CDS" label="CDS" />
                  </div>
                </div>
              </div>

              <DialogFooter>
                <Button variant="ghost" onClick={clearFilters}>
                  Clear All
                </Button>
                <Button onClick={() => setSettingsOpen(false)}>Done</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          <Button
            variant="outline"
            size="sm"
            onClick={() => fetchPositions(true)}
            disabled={isRefreshing}
          >
            <RefreshCw className={cn('h-4 w-4 mr-2', isRefreshing && 'animate-spin')} />
            Refresh
          </Button>

          <Button variant="outline" size="sm" onClick={exportToCSV}>
            <Download className="h-4 w-4 mr-2" />
            Export
          </Button>

          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="destructive" size="sm" disabled={stats.total === 0}>
                <X className="h-4 w-4 mr-2" />
                Close All
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Close All Positions?</AlertDialogTitle>
                <AlertDialogDescription>
                  This will close all {stats.total} open positions at market price. This action
                  cannot be undone.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={handleCloseAllPositions}>Close All</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </div>

      {/* Active Filters Bar */}
      {hasActiveFilters && (
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm text-muted-foreground">Active Filters:</span>
          {grouping !== 'none' && (
            <Badge variant="secondary" className="bg-pink-500/10 text-pink-600 border-pink-500/30">
              Grouped: {grouping === 'underlying' ? 'Underlying' : 'Underlying & Expiry'}
            </Badge>
          )}
          {selectedStrategy !== 'all' && (
            <Badge
              variant="secondary"
              className="bg-primary/10 text-primary border-primary/30 flex items-center gap-1"
            >
              Strategy: {selectedStrategy}
              <X
                className="h-3 w-3 cursor-pointer hover:text-destructive"
                onClick={() => setSelectedStrategy('all')}
              />
            </Badge>
          )}
          {!isCrypto &&
            filters.product.map((v) => (
              <Badge
                key={v}
                variant="secondary"
                className="bg-pink-500/10 text-pink-600 border-pink-500/30"
              >
                {v}
              </Badge>
            ))}
          {filters.direction.map((v) => (
            <Badge
              key={v}
              variant="secondary"
              className="bg-pink-500/10 text-pink-600 border-pink-500/30"
            >
              {v}
            </Badge>
          ))}
          {filters.exchange.map((v) => (
            <Badge
              key={v}
              variant="secondary"
              className="bg-pink-500/10 text-pink-600 border-pink-500/30"
            >
              {v}
            </Badge>
          ))}
          <Button
            variant="outline"
            size="sm"
            className="text-red-500 border-red-500/50 hover:bg-red-500/10"
            onClick={clearFilters}
          >
            Clear All
          </Button>
        </div>
      )}

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Open Positions</CardDescription>
            <CardTitle className="text-2xl">{stats.total}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Long</CardDescription>
            <CardTitle className="text-2xl text-green-600">{stats.long}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Short</CardDescription>
            <CardTitle className="text-2xl text-red-600">{stats.short}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Total P&L</CardDescription>
            <CardTitle
              className={cn(
                'text-2xl font-mono',
                isProfit(stats.totalPnl) ? 'text-green-600' : 'text-red-600'
              )}
            >
              {stats.totalPnl >= 0 ? '+' : ''}
              {formatCurrency(stats.totalPnl)}
            </CardTitle>
          </CardHeader>
        </Card>
      </div>

      {/* Strategy Attribution Overview Cards */}
      {strategyStats.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
              <Layers className="h-4 w-4 text-muted-foreground" />
              Strategy Overview
            </h3>
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={expandAll}>
                Expand All Contracts
              </Button>
              <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={collapseAll}>
                Collapse All
              </Button>
            </div>
          </div>
          <div className="grid gap-3 grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
            {strategyStats.map((s) => {
              const isSelected = selectedStrategy.toLowerCase() === s.name.toLowerCase()
              return (
                <Card
                  key={s.name}
                  onClick={() => {
                    if (selectedStrategy.toLowerCase() === s.name.toLowerCase()) {
                      setSelectedStrategy('all')
                    } else {
                      setSelectedStrategy(s.name)
                      if (s.count === 0 && (s.closedCount ?? 0) > 0) {
                        setPositionsTab('closed')
                      }
                    }
                  }}
                  className={cn(
                    'cursor-pointer transition-all hover:border-primary/50 hover:shadow-xs',
                    isSelected && 'ring-2 ring-primary border-primary bg-primary/5'
                  )}
                >
                  <CardHeader className="p-3 pb-1">
                    <CardDescription
                      className="text-xs font-semibold truncate text-foreground"
                      title={s.name}
                    >
                      {s.name}
                    </CardDescription>
                    <CardTitle
                      className={cn(
                        'text-base font-bold font-mono',
                        s.totalPnl >= 0 ? 'text-green-600' : 'text-red-600'
                      )}
                    >
                      {s.totalPnl >= 0 ? '+' : ''}
                      {formatCurrency(s.totalPnl)}
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-3 pt-0 text-[11px] text-muted-foreground flex items-center justify-between">
                    <span>
                      {s.count > 0 && (s.closedCount ?? 0) > 0
                        ? `${s.count} open · ${s.closedCount} closed`
                        : s.count > 0
                        ? `${s.count} ${s.count === 1 ? 'leg' : 'legs'}`
                        : (s.closedCount ?? 0) > 0
                        ? `${s.closedCount} closed`
                        : '0 positions'}
                    </span>
                    <Badge
                      variant="outline"
                      className={cn(
                        'text-[10px] px-1 py-0',
                        isSelected
                          ? 'bg-primary text-primary-foreground border-transparent'
                          : 'text-muted-foreground'
                      )}
                    >
                      {isSelected ? 'Filtered' : 'Filter'}
                    </Badge>
                  </CardContent>
                </Card>
              )
            })}
          </div>
        </div>
      )}

      {/* Positions Tabs & Tables */}
      <Tabs
        value={positionsTab}
        onValueChange={(val) => setPositionsTab(val as 'active' | 'closed')}
        className="space-y-3"
      >
        <div className="flex items-center justify-between">
          <TabsList className="grid grid-cols-2 w-[280px]">
            <TabsTrigger value="active" className="gap-2">
              <span>Active</span>
              <Badge variant="secondary" className="text-[11px] px-1.5 py-0">
                {filteredPositions.length}
              </Badge>
            </TabsTrigger>
            <TabsTrigger value="closed" className="gap-2">
              <span>Closed</span>
              <Badge variant="secondary" className="text-[11px] px-1.5 py-0">
                {filteredClosedPositions.length}
              </Badge>
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="active" className="mt-0">
          <Card>
            <CardContent className="py-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin" />
            </div>
          ) : error ? (
            <div className="text-center py-12 text-muted-foreground">{error}</div>
          ) : filteredPositions.length === 0 ? (
            <EmptyState
              icon={ChartCandlestick}
              title={hasActiveFilters ? 'No positions match your filters' : 'No active positions'}
              description={
                hasActiveFilters
                  ? 'Try adjusting or clearing your filters to see results.'
                  : 'Account is currently FLAT'
              }
              action={
                hasActiveFilters ? (
                  <Button variant="ghost" size="sm" onClick={clearFilters}>
                    Clear Filters
                  </Button>
                ) : undefined
              }
            />
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <SortableHeader column={0} label="Symbol / Contract" className="w-[260px]" />
                    <TableHead className="w-[80px]">Exchange</TableHead>
                    {!isCrypto && <TableHead className="w-[80px]">Product</TableHead>}
                    <SortableHeader
                      column={3}
                      label="Broker Net"
                      className="w-[100px] text-right"
                    />
                    <SortableHeader column={4} label="Avg Price" className="w-[110px] text-right" />
                    <TableHead className="w-[110px] text-right">LTP</TableHead>
                    <SortableHeader column={6} label="P&L" className="w-[120px] text-right" />
                    <SortableHeader column={7} label="P&L %" className="w-[90px] text-right" />
                    <TableHead className="w-[70px] text-right">Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sortedGroupKeys.map((groupKey) => {
                    const groupPositions = groupedPositions[groupKey]
                    const isCollapsed = collapsedGroups.has(groupKey)
                    const groupStats = calculateGroupStats(groupPositions)

                    return (
                      <React.Fragment key={groupKey}>
                        {/* Group Header Row */}
                        {grouping !== 'none' && (
                          <TableRow
                            className="bg-muted/50 cursor-pointer hover:bg-muted"
                            onClick={() => toggleGroup(groupKey)}
                          >
                            <TableCell colSpan={isCrypto ? 5 : 6}>
                              <div className="flex items-center gap-3 py-1 font-semibold">
                                {isCollapsed ? (
                                  <ChevronRight className="h-4 w-4 text-muted-foreground" />
                                ) : (
                                  <ChevronDown className="h-4 w-4 text-muted-foreground" />
                                )}
                                <span>{groupKey}</span>
                                <Badge variant="outline" className="text-xs">
                                  {groupStats.count}
                                </Badge>
                              </div>
                            </TableCell>
                            <TableCell
                              className={cn(
                                'text-right font-bold font-mono',
                                isProfit(groupStats.totalPnl) ? 'text-green-600' : 'text-red-600'
                              )}
                            >
                              {groupStats.totalPnl >= 0 ? '+' : ''}
                              {formatCurrency(groupStats.totalPnl)}
                            </TableCell>
                            <TableCell
                              className={cn(
                                'text-right font-semibold font-mono',
                                isProfit(groupStats.pnlPercent) ? 'text-green-600' : 'text-red-600'
                              )}
                            >
                              {groupStats.pnlPercent >= 0 ? '+' : ''}
                              {groupStats.pnlPercent.toFixed(2)}%
                            </TableCell>
                            <TableCell />
                          </TableRow>
                        )}

                        {/* Position Rows */}
                        {!isCollapsed &&
                          groupPositions.map((position, index) => {
                            // A broker keeps reporting a position it has
                            // squared off, with quantity 0 and its realised
                            // P&L. Those rows stay - the figure is the point -
                            // but there is nothing left to close on them.
                            //
                            // Coerced, not compared directly: the quantity is
                            // typed as a number but does not always arrive as
                            // one. Zerodha's position mapping defaults it to
                            // the string "0", and a strict `!== 0` reads that
                            // as an open position, which is the exact row this
                            // guard exists to catch. calculatePnlPercent above
                            // coerces for the same reason.
                            const quantity = Number(position.quantity) || 0
                            const isOpen = quantity !== 0

                            const cKey = getContractKey(
                              position.symbol,
                              position.exchange,
                              position.product
                            )
                            const contractRec = contractRecMap.get(cKey)
                            const allLegs = contractLegsMap.get(cKey) || []
                            const legs =
                              selectedStrategy !== 'all'
                                ? allLegs.filter(
                                    (l) =>
                                      l.strategy.toLowerCase() === selectedStrategy.toLowerCase()
                                  )
                                : allLegs
                            const isExpanded = expandedContracts.has(cKey)

                            return (
                              <React.Fragment
                                key={`${position.symbol}-${position.exchange}-${position.product}-${index}`}
                              >
                                <TableRow className={cn(isExpanded && 'bg-muted/20')}>
                                  {/* Symbol Cell with Expansion & Reconciliation info */}
                                  <TableCell className="w-[260px]">
                                    <div className="flex items-start gap-2">
                                      <Button
                                        variant="ghost"
                                        size="sm"
                                        className="h-6 w-6 p-0 hover:bg-muted shrink-0 mt-0.5"
                                        onClick={() => toggleExpand(cKey)}
                                        aria-label={
                                          isExpanded
                                            ? `Collapse ${position.symbol}`
                                            : `Expand ${position.symbol}`
                                        }
                                      >
                                        {isExpanded ? (
                                          <ChevronDown className="h-4 w-4 text-muted-foreground" />
                                        ) : (
                                          <ChevronRight className="h-4 w-4 text-muted-foreground" />
                                        )}
                                      </Button>
                                      <div className="space-y-1">
                                        <div className="flex items-center gap-2">
                                          <span className="font-semibold text-foreground">
                                            {position.symbol}
                                          </span>
                                          {contractRec && (
                                            <Badge
                                              variant="outline"
                                              className={cn(
                                                'text-[10px] px-1.5 py-0 font-medium tracking-wide',
                                                contractRec.reconciliation_status === 'RECONCILED'
                                                  ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30'
                                                  : 'bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/30 font-bold'
                                              )}
                                            >
                                              {contractRec.reconciliation_status === 'RECONCILED'
                                                ? '✓ RECONCILED'
                                                : '⚠ MISMATCH'}
                                            </Badge>
                                          )}
                                        </div>
                                        {/* Reconciliation quantities strip */}
                                        {contractRec && (
                                          <div className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[11px] text-muted-foreground font-mono">
                                            <span>
                                              Broker Net:{' '}
                                              <strong className="text-foreground">
                                                {contractRec.broker_quantity}
                                              </strong>
                                            </span>
                                            <span>•</span>
                                            <span>
                                              Tracked:{' '}
                                              <strong className="text-foreground">
                                                {contractRec.tracked_quantity}
                                              </strong>
                                            </span>
                                            {Math.abs(contractRec.residual_quantity) > 1e-6 && (
                                              <>
                                                <span>•</span>
                                                <span className="text-amber-600 dark:text-amber-400">
                                                  Manual:{' '}
                                                  <strong>{contractRec.residual_quantity}</strong>
                                                </span>
                                              </>
                                            )}
                                          </div>
                                        )}
                                      </div>
                                    </div>
                                  </TableCell>
                                  <TableCell className="w-[80px]">
                                    <Badge
                                      variant="outline"
                                      className={EXCHANGE_COLORS[position.exchange] || ''}
                                    >
                                      {position.exchange}
                                    </Badge>
                                  </TableCell>
                                  {!isCrypto && (
                                    <TableCell className="w-[80px]">
                                      <Badge
                                        variant="outline"
                                        className={PRODUCT_COLORS[position.product] || ''}
                                      >
                                        {position.product}
                                      </Badge>
                                    </TableCell>
                                  )}
                                  <TableCell
                                    className={cn(
                                      'w-[100px] text-right font-medium font-mono',
                                      !isOpen
                                        ? 'text-muted-foreground'
                                        : quantity > 0
                                          ? 'text-green-600'
                                          : 'text-red-600'
                                    )}
                                  >
                                    {position.quantity}
                                  </TableCell>
                                  <TableCell className="w-[110px] text-right font-mono">
                                    {formatCurrency(position.average_price)}
                                  </TableCell>
                                  <TableCell className="w-[110px] text-right font-mono">
                                    {position.ltp !== undefined
                                      ? formatCurrency(position.ltp)
                                      : '-'}
                                  </TableCell>
                                  <TableCell
                                    className={cn(
                                      'w-[120px] text-right font-medium',
                                      isProfit(position.pnl) ? 'text-green-600' : 'text-red-600'
                                    )}
                                  >
                                    <div className="flex items-center justify-end gap-1 font-mono">
                                      {isProfit(position.pnl) ? (
                                        <TrendingUp className="h-4 w-4" />
                                      ) : (
                                        <TrendingDown className="h-4 w-4" />
                                      )}
                                      {formatCurrency(position.pnl)}
                                    </div>
                                  </TableCell>
                                  <TableCell
                                    className={cn(
                                      'w-[90px] text-right font-mono',
                                      isProfit(calculatePnlPercent(position))
                                        ? 'text-green-600'
                                        : 'text-red-600'
                                    )}
                                  >
                                    {calculatePnlPercent(position) >= 0 ? '+' : ''}
                                    {calculatePnlPercent(position).toFixed(2)}%
                                  </TableCell>
                                  <TableCell className="w-[70px] text-right">
                                    {isOpen && (
                                      <Button
                                        variant="ghost"
                                        size="sm"
                                        className="text-destructive hover:text-destructive hover:bg-destructive/10"
                                        onClick={() => handleClosePosition(position)}
                                        aria-label={`Close ${position.symbol} position`}
                                      >
                                        <X className="h-4 w-4" />
                                      </Button>
                                    )}
                                  </TableCell>
                                </TableRow>

                                {/* Strategy Attribution Accordion Row */}
                                {isExpanded && (
                                  <TableRow className="bg-muted/10 hover:bg-muted/15 border-b border-border/50">
                                    <TableCell
                                      colSpan={isCrypto ? 8 : 9}
                                      className="p-0 pl-10 pr-4 py-3"
                                    >
                                      <div className="rounded-md border border-border/60 bg-background/95 overflow-hidden shadow-xs">
                                        <div className="bg-muted/40 px-3 py-1.5 border-b border-border/40 flex items-center justify-between">
                                          <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                                            <Layers className="h-3.5 w-3.5 text-muted-foreground" />
                                            Strategy Position Attribution
                                          </span>
                                          <span className="text-xs text-muted-foreground font-medium">
                                            {legs.length} {legs.length === 1 ? 'record' : 'records'}
                                          </span>
                                        </div>
                                        <Table>
                                          <TableHeader>
                                            <TableRow className="hover:bg-transparent border-b border-border/40 text-xs">
                                              <TableHead className="py-2 h-8">Strategy</TableHead>
                                              <TableHead className="py-2 h-8 text-right">
                                                Qty
                                              </TableHead>
                                              <TableHead className="py-2 h-8 text-center">
                                                Side
                                              </TableHead>
                                              <TableHead className="py-2 h-8 text-right">
                                                Avg Price
                                              </TableHead>
                                              <TableHead className="py-2 h-8 text-right">
                                                LTP
                                              </TableHead>
                                              <TableHead className="py-2 h-8 text-right">
                                                P&L
                                              </TableHead>
                                              <TableHead className="py-2 h-8 text-right">
                                                P&L %
                                              </TableHead>
                                            </TableRow>
                                          </TableHeader>
                                          <TableBody>
                                            {legs.length === 0 ? (
                                              <TableRow>
                                                <TableCell
                                                  colSpan={7}
                                                  className="text-center py-4 text-xs text-muted-foreground"
                                                >
                                                  No strategy attribution records found for this
                                                  contract.
                                                </TableCell>
                                              </TableRow>
                                            ) : (
                                              legs.map((leg, legIdx) => {
                                                const liveLtp = position.ltp ?? leg.ltp
                                                const sQty = leg.signed_quantity
                                                const sAvg = leg.average_price
                                                const sRealized = leg.realized_pnl

                                                let sUnrealized = leg.unrealized_pnl
                                                if (
                                                  liveLtp !== undefined &&
                                                  liveLtp > 0 &&
                                                  Math.abs(sQty) > 1e-9
                                                ) {
                                                  sUnrealized = sQty * (liveLtp - sAvg)
                                                }
                                                const sTotal = sRealized + sUnrealized
                                                const investment = Math.abs(sAvg * sQty)
                                                const sPnlPercent =
                                                  investment > 0 ? (sTotal / investment) * 100 : 0

                                                const isManual =
                                                  leg.strategy === 'Manual / Unattributed'

                                                return (
                                                  <TableRow
                                                    key={`${leg.strategy}-${legIdx}`}
                                                    className="text-xs hover:bg-muted/40"
                                                  >
                                                    <TableCell className="py-2 font-medium">
                                                      {isManual ? (
                                                        <span className="inline-flex items-center gap-1.5 text-amber-600 dark:text-amber-400 font-medium">
                                                          <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
                                                          Manual / Unattributed
                                                        </span>
                                                      ) : (
                                                        <span className="inline-flex items-center gap-1.5 font-semibold text-foreground">
                                                          <span className="w-1.5 h-1.5 rounded-full bg-primary" />
                                                          {leg.strategy}
                                                        </span>
                                                      )}
                                                    </TableCell>
                                                    <TableCell
                                                      className={cn(
                                                        'py-2 text-right font-mono font-medium',
                                                        sQty > 0
                                                          ? 'text-green-600'
                                                          : sQty < 0
                                                            ? 'text-red-600'
                                                            : 'text-muted-foreground'
                                                      )}
                                                    >
                                                      {leg.signed_quantity}
                                                    </TableCell>
                                                    <TableCell className="py-2 text-center">
                                                      <Badge
                                                        variant="outline"
                                                        className={cn(
                                                          'text-[10px] px-1.5 py-0 font-semibold',
                                                          leg.side === 'LONG'
                                                            ? 'bg-emerald-500/10 text-emerald-600 border-emerald-500/30'
                                                            : leg.side === 'SHORT'
                                                              ? 'bg-red-500/10 text-red-600 border-red-500/30'
                                                              : 'bg-muted text-muted-foreground'
                                                        )}
                                                      >
                                                        {leg.side}
                                                      </Badge>
                                                    </TableCell>
                                                    <TableCell className="py-2 text-right font-mono">
                                                      {formatCurrency(leg.average_price)}
                                                    </TableCell>
                                                    <TableCell className="py-2 text-right font-mono">
                                                      {liveLtp !== undefined
                                                        ? formatCurrency(liveLtp)
                                                        : '-'}
                                                    </TableCell>
                                                    <TableCell
                                                      className={cn(
                                                        'py-2 text-right font-mono font-medium',
                                                        isProfit(sTotal)
                                                          ? 'text-green-600'
                                                          : 'text-red-600'
                                                      )}
                                                    >
                                                      {sTotal >= 0 ? '+' : ''}
                                                      {formatCurrency(sTotal)}
                                                    </TableCell>
                                                    <TableCell
                                                      className={cn(
                                                        'py-2 text-right font-mono',
                                                        isProfit(sPnlPercent)
                                                          ? 'text-green-600'
                                                          : 'text-red-600'
                                                      )}
                                                    >
                                                      {sPnlPercent >= 0 ? '+' : ''}
                                                      {sPnlPercent.toFixed(2)}%
                                                    </TableCell>
                                                  </TableRow>
                                                )
                                              })
                                            )}
                                          </TableBody>
                                        </Table>
                                      </div>
                                    </TableCell>
                                  </TableRow>
                                )}
                              </React.Fragment>
                            )
                          })}
                      </React.Fragment>
                    )
                  })}
                </TableBody>
                <TableFooter>
                  <TableRow className="bg-muted/50">
                    <TableCell
                      colSpan={isCrypto ? 5 : 6}
                      className="text-right text-muted-foreground"
                    >
                      Total P&L:
                    </TableCell>
                    <TableCell
                      className={cn(
                        'w-[120px] text-right font-bold font-mono',
                        isProfit(stats.totalPnl) ? 'text-green-600' : 'text-red-600'
                      )}
                    >
                      {stats.totalPnl >= 0 ? '+' : ''}
                      {formatCurrency(stats.totalPnl)}
                    </TableCell>
                    <TableCell colSpan={2} />
                  </TableRow>
                </TableFooter>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </TabsContent>

    <TabsContent value="closed" className="mt-0">
      <Card>
        <CardContent className="py-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin" />
            </div>
          ) : error ? (
            <div className="text-center py-12 text-muted-foreground">{error}</div>
          ) : filteredClosedPositions.length === 0 ? (
            <EmptyState
              icon={ChartCandlestick}
              title={
                selectedStrategy !== 'all'
                  ? `No closed positions for ${selectedStrategy}`
                  : 'No closed positions today'
              }
              description={
                selectedStrategy !== 'all'
                  ? 'Completed round-trip trades for this strategy will appear here.'
                  : 'Completed round-trip trades from today’s session will appear here.'
              }
              action={
                selectedStrategy !== 'all' ? (
                  <Button variant="ghost" size="sm" onClick={() => setSelectedStrategy('all')}>
                    Show All Strategies
                  </Button>
                ) : undefined
              }
            />
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[140px]">Strategy</TableHead>
                    <TableHead className="w-[200px]">Symbol / Contract</TableHead>
                    <TableHead className="w-[80px]">Exchange</TableHead>
                    {!isCrypto && <TableHead className="w-[80px]">Product</TableHead>}
                    <TableHead className="w-[90px]">Direction</TableHead>
                    <TableHead className="w-[90px] text-right">Quantity</TableHead>
                    <TableHead className="w-[100px] text-right">Entry Avg</TableHead>
                    <TableHead className="w-[100px] text-right">Exit Avg</TableHead>
                    <TableHead className="w-[140px] text-center">Entry Time</TableHead>
                    <TableHead className="w-[140px] text-center">Exit Time</TableHead>
                    <TableHead className="w-[120px] text-right">Realized P&L</TableHead>
                    <TableHead className="w-[80px] text-center">Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredClosedPositions.map((pos, idx) => {
                    const isWin = pos.realized_pnl >= 0
                    return (
                      <TableRow key={`${pos.strategy}-${pos.symbol}-${pos.exit_time}-${idx}`}>
                        <TableCell>
                          <Badge
                            variant="outline"
                            className="font-semibold text-xs text-primary border-primary/30 bg-primary/5"
                          >
                            {pos.strategy}
                          </Badge>
                        </TableCell>
                        <TableCell className="font-semibold font-mono">
                          {pos.symbol}
                        </TableCell>
                        <TableCell>
                          <Badge variant="secondary" className="text-xs">
                            {pos.exchange}
                          </Badge>
                        </TableCell>
                        {!isCrypto && (
                          <TableCell>
                            <Badge variant="outline" className="text-xs">
                              {pos.product}
                            </Badge>
                          </TableCell>
                        )}
                        <TableCell>
                          <Badge
                            variant="outline"
                            className={cn(
                              'text-xs font-semibold',
                              pos.direction === 'LONG'
                                ? 'border-green-500/30 text-green-600 bg-green-500/10'
                                : 'border-red-500/30 text-red-600 bg-red-500/10'
                            )}
                          >
                            {pos.direction}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right font-mono font-medium">
                          {pos.quantity}
                        </TableCell>
                        <TableCell className="text-right font-mono">
                          {formatCurrency(pos.entry_average)}
                        </TableCell>
                        <TableCell className="text-right font-mono">
                          {formatCurrency(pos.exit_average)}
                        </TableCell>
                        <TableCell className="text-center text-xs text-muted-foreground font-mono">
                          {pos.entry_time || '—'}
                        </TableCell>
                        <TableCell className="text-center text-xs text-muted-foreground font-mono">
                          {pos.exit_time || '—'}
                        </TableCell>
                        <TableCell
                          className={cn(
                            'text-right font-mono font-bold',
                            isWin ? 'text-green-600' : 'text-red-600'
                          )}
                        >
                          {pos.realized_pnl >= 0 ? '+' : ''}
                          {formatCurrency(pos.realized_pnl)}
                        </TableCell>
                        <TableCell className="text-center">
                          <Badge
                            variant="outline"
                            className="text-[10px] text-muted-foreground bg-muted/40"
                          >
                            {pos.exit_reason ? `CLOSED (${pos.exit_reason})` : 'CLOSED'}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
                <TableFooter>
                  <TableRow className="bg-muted/50">
                    <TableCell
                      colSpan={isCrypto ? 9 : 10}
                      className="text-right text-muted-foreground font-medium"
                    >
                      Total Realized P&L:
                    </TableCell>
                    <TableCell
                      className={cn(
                        'text-right font-bold font-mono',
                        totalClosedPnl >= 0 ? 'text-green-600' : 'text-red-600'
                      )}
                    >
                      {totalClosedPnl >= 0 ? '+' : ''}
                      {formatCurrency(totalClosedPnl)}
                    </TableCell>
                    <TableCell />
                  </TableRow>
                </TableFooter>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </TabsContent>
  </Tabs>
    </div>
  )
}
