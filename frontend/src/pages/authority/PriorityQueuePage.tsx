import { ListOrdered, RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { PriorityQueueList } from '../../components/PriorityQueue'
import { RiskDetail } from '../../components/RiskDetail'
import { Button, ErrorBlock, LoadingBlock, Panel, StaleNotice } from '../../components/ui'
import { api } from '../../lib/api'
import { useApi } from '../../lib/hooks'
import { useI18n } from '../../lib/i18n'

export default function PriorityQueuePage() {
  const { lang } = useI18n()
  const [params, setParams] = useSearchParams()
  const selected = params.get('location')

  const overview = useApi(() => api.overview())
  const [autoSelected, setAutoSelected] = useState(false)

  useEffect(() => {
    if (autoSelected || selected || !overview.data?.priority_queue?.length) return
    setParams({ location: overview.data.priority_queue[0].location_id }, { replace: true })
    setAutoSelected(true)
  }, [overview.data, selected, autoSelected, setParams])

  const risk = useApi(
    (signal) => api.risk(selected!, { detail: true, lang }, signal),
    { enabled: !!selected, deps: [selected, lang] },
  )

  return (
    <div className="grid min-h-0 gap-3 p-3 lg:h-full lg:grid-cols-[26rem_1fr] lg:p-4">
      <div className="flex min-h-0 flex-col gap-2">
        <StaleNotice stale={overview.stale} />
        <Panel
          title="Priority queue"
          subtitle={`${overview.data?.priority_queue?.length ?? 0} areas ranked`}
          icon={<ListOrdered size={14} className="text-ink-400" />}
          actions={
            <Button size="sm" variant="ghost" icon={<RefreshCw size={12} />} onClick={overview.reload} title="Refresh" />
          }
          dense
          className="min-h-0 flex-1"
          bodyClassName="overflow-y-auto"
        >
          {overview.loading && !overview.data ? (
            <div className="p-3">
              <LoadingBlock rows={8} />
            </div>
          ) : overview.data ? (
            <PriorityQueueList
              entries={overview.data.priority_queue}
              selectedId={selected}
              onSelect={(id) => setParams({ location: id })}
            />
          ) : (
            <div className="p-3">
              <ErrorBlock error={overview.error} onRetry={overview.reload} />
            </div>
          )}
        </Panel>
      </div>

      <div className="min-h-0 overflow-y-auto">
        {!selected ? (
          <Panel>
            <p className="text-sm text-ink-400">Select an area from the queue to see its full assessment.</p>
          </Panel>
        ) : risk.loading && !risk.data ? (
          <div className="space-y-3">
            <LoadingBlock rows={4} />
            <LoadingBlock rows={6} />
          </div>
        ) : risk.data ? (
          <>
            <StaleNotice stale={risk.stale} />
            <RiskDetail risk={risk.data} />
          </>
        ) : (
          <ErrorBlock error={risk.error} onRetry={risk.reload} />
        )}
      </div>
    </div>
  )
}
