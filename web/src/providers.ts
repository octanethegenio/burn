import anthropicSvg from '@lobehub/icons-static-svg/icons/anthropic.svg?raw'
import cursorSvg from '@lobehub/icons-static-svg/icons/cursor.svg?raw'
import deepseekSvg from '@lobehub/icons-static-svg/icons/deepseek.svg?raw'
import googleSvg from '@lobehub/icons-static-svg/icons/google.svg?raw'
import grokSvg from '@lobehub/icons-static-svg/icons/grok.svg?raw'
import moonshotSvg from '@lobehub/icons-static-svg/icons/moonshot.svg?raw'
import openaiSvg from '@lobehub/icons-static-svg/icons/openai.svg?raw'
import zaiSvg from '@lobehub/icons-static-svg/icons/zai.svg?raw'
import type { ModelRow } from './api'

export type ProviderId =
  | 'cursor'
  | 'anthropic'
  | 'openai'
  | 'google'
  | 'xai'
  | 'moonshot'
  | 'zhipu'
  | 'deepseek'
  | 'other'

export type ProviderInfo = {
  id: ProviderId
  name: string
  iconSrc: string | null
}

const svgSrc = (svg: string) => `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`

const PROVIDERS: Record<ProviderId, ProviderInfo> = {
  cursor: { id: 'cursor', name: 'Cursor (first-party)', iconSrc: svgSrc(cursorSvg) },
  anthropic: { id: 'anthropic', name: 'Anthropic', iconSrc: svgSrc(anthropicSvg) },
  openai: { id: 'openai', name: 'OpenAI', iconSrc: svgSrc(openaiSvg) },
  google: { id: 'google', name: 'Google', iconSrc: svgSrc(googleSvg) },
  xai: { id: 'xai', name: 'xAI', iconSrc: svgSrc(grokSvg) },
  moonshot: { id: 'moonshot', name: 'Moonshot', iconSrc: svgSrc(moonshotSvg) },
  zhipu: { id: 'zhipu', name: 'Zhipu', iconSrc: svgSrc(zaiSvg) },
  deepseek: { id: 'deepseek', name: 'DeepSeek', iconSrc: svgSrc(deepseekSvg) },
  other: { id: 'other', name: 'Other', iconSrc: null },
}

export type ModelSortKey =
  | 'model'
  | 'request_count'
  | 'input_tokens'
  | 'output_tokens'
  | 'cache_read_tokens'
  | 'cost_usd'

function looksFirstPartyByName(model: string): boolean {
  const m = model.toLowerCase()
  if (m.includes('composer')) return true
  if (m.startsWith('cursor-')) return true
  // Aggregate labels for included Grok 4.5 (not API Grok Build)
  if (/^grok-4\.5/.test(m)) return true
  return false
}

/** Cursor billing tier: 2 = first-party pool, 1 = API pool. */
export function isFirstParty(row: ModelRow): boolean {
  if (row.tier === 2) return true
  if (row.tier === 1) return false
  return looksFirstPartyByName(row.model)
}

function providerFromApiName(model: string): ProviderInfo {
  const m = model.toLowerCase()
  if (m.includes('grok') || m.includes('xai')) return PROVIDERS.xai
  if (
    m.includes('claude') ||
    m.includes('fable') ||
    m.includes('sonnet') ||
    m.includes('opus') ||
    m.includes('haiku')
  ) {
    return PROVIDERS.anthropic
  }
  if (m.includes('gpt') || /(^|-)o[0-9]/.test(m)) return PROVIDERS.openai
  if (m.includes('gemini')) return PROVIDERS.google
  if (m.includes('kimi') || m.includes('moonshot')) return PROVIDERS.moonshot
  if (m.includes('glm') || m.includes('zhipu') || m.includes('chatglm')) return PROVIDERS.zhipu
  if (m.includes('deepseek')) return PROVIDERS.deepseek
  if (m.includes('composer') || m.includes('cursor')) return PROVIDERS.cursor
  return PROVIDERS.other
}

export function providerForModel(row: ModelRow): ProviderInfo {
  if (isFirstParty(row)) return PROVIDERS.cursor
  return providerFromApiName(row.model)
}

export type ProviderGroup = {
  provider: ProviderInfo
  models: ModelRow[]
  cost_usd: number
  request_count: number
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
}

function cmpNum(a: number, b: number, dir: number) {
  return (a - b) * dir
}

function groupMetric(g: ProviderGroup, key: ModelSortKey): number | string {
  switch (key) {
    case 'model':
      return g.provider.name.toLowerCase()
    case 'cost_usd':
      return g.cost_usd
    case 'request_count':
      return g.request_count
    case 'input_tokens':
      return g.input_tokens
    case 'output_tokens':
      return g.output_tokens
    case 'cache_read_tokens':
      return g.cache_read_tokens
  }
}

export function groupModelsByProvider(
  models: ModelRow[],
  sortKey: ModelSortKey = 'cost_usd',
  sortDir: 'asc' | 'desc' = 'desc',
): ProviderGroup[] {
  const map = new Map<ProviderId, ProviderGroup>()
  for (const row of models) {
    const p = providerForModel(row)
    let g = map.get(p.id)
    if (!g) {
      g = {
        provider: p,
        models: [],
        cost_usd: 0,
        request_count: 0,
        input_tokens: 0,
        output_tokens: 0,
        cache_read_tokens: 0,
      }
      map.set(p.id, g)
    }
    g.models.push(row)
    g.cost_usd += row.cost_usd
    g.request_count += row.request_count || 0
    g.input_tokens += row.input_tokens || 0
    g.output_tokens += row.output_tokens || 0
    g.cache_read_tokens += row.cache_read_tokens || 0
  }

  const dir = sortDir === 'asc' ? 1 : -1

  for (const g of map.values()) {
    g.models.sort((a, b) => {
      if (sortKey === 'model') return a.model.localeCompare(b.model) * dir
      return cmpNum(a[sortKey] as number, b[sortKey] as number, dir)
    })
  }

  return [...map.values()].sort((a, b) => {
    const av = groupMetric(a, sortKey)
    const bv = groupMetric(b, sortKey)
    if (typeof av === 'string' && typeof bv === 'string') {
      return av.localeCompare(bv) * dir
    }
    return cmpNum(av as number, bv as number, dir)
  })
}
