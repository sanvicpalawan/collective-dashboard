'use client'

import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post, apiErrorMessage } from '@/lib/api'
import PageHeader from '@/components/ui/PageHeader'
import Button from '@/components/ui/Button'
import Badge, { type BadgeVariant } from '@/components/ui/Badge'
import LoadingSpinner from '@/components/ui/LoadingSpinner'
import toast from 'react-hot-toast'
import { Search, MapPin, Building2, Mail, Phone, Loader2, Users } from 'lucide-react'

interface Lead {
  id: string
  businessName: string
  email?: string | null
  phone?: string | null
  status: string
  niche?: string | null
  location?: string | null
  source?: string | null
  createdAt?: string | null
}

interface LeadJob {
  id: string
  status: string
  result?: { created?: number; requested?: number; skipped?: number } | null
  error?: string | null
  createdAt?: string | null
  completedAt?: string | null
}

const STATUS_VARIANT: Record<string, BadgeVariant> = {
  new: 'info',
  contacted: 'warning',
  qualified: 'success',
  won: 'success',
  lost: 'gray',
}

/** Poll a queued job until the worker finishes it. */
const POLL_INTERVAL_MS = 1500
const POLL_MAX_ATTEMPTS = 40 // ~60s

export default function LeadsPage() {
  const qc = useQueryClient()
  const [niche, setNiche] = useState('')
  const [location, setLocation] = useState('')
  const [job, setJob] = useState<LeadJob | null>(null)
  const [running, setRunning] = useState(false)

  const { data, isLoading } = useQuery<Lead[]>({
    queryKey: ['leads'],
    queryFn: () => get<Lead[]>('/api/leads'),
  })
  const leads = data ?? []

  function pollJob(id: string) {
    let attempts = 0
    const tick = async () => {
      attempts += 1
      try {
        const current = await get<LeadJob>(`/api/leads/jobs/${id}`)
        setJob(current)
        if (current.status === 'succeeded') {
          setRunning(false)
          qc.invalidateQueries({ queryKey: ['leads'] })
          const found = current.result?.created ?? 0
          toast.success(found > 0 ? `Found ${found} leads` : 'Search finished — no new leads')
          return
        }
        if (current.status === 'failed' || current.status === 'cancelled') {
          setRunning(false)
          toast.error(current.error ?? 'The search failed')
          return
        }
        if (attempts >= POLL_MAX_ATTEMPTS) {
          setRunning(false)
          toast.error('The worker is taking longer than usual — reload in a moment')
          return
        }
        setTimeout(tick, POLL_INTERVAL_MS)
      } catch (err) {
        setRunning(false)
        toast.error(apiErrorMessage(err, 'Could not read the search status'))
      }
    }
    setTimeout(tick, POLL_INTERVAL_MS)
  }

  async function startSearch(e: React.FormEvent) {
    e.preventDefault()
    if (niche.trim().length < 2 || location.trim().length < 2) {
      toast.error('Enter a niche and a location')
      return
    }
    setRunning(true)
    try {
      const created = await post<LeadJob>('/api/leads/find', {
        niche: niche.trim(),
        location: location.trim(),
      })
      setJob(created)
      pollJob(created.id)
    } catch (err) {
      setRunning(false)
      toast.error(apiErrorMessage(err, 'Could not queue the search'))
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Lead Generation"
        subtitle="Find businesses in a niche and location, then work them from one table."
      />

      {/* Search */}
      <section className="card p-5 md:p-6">
        <form onSubmit={startSearch} className="flex flex-col gap-4 lg:flex-row lg:items-end">
          <div className="flex-1">
            <label htmlFor="niche" className="label">Niche</label>
            <div className="relative mt-1.5">
              <Building2 size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-mute" />
              <input
                id="niche"
                value={niche}
                onChange={(e) => setNiche(e.target.value)}
                placeholder="dentists"
                className="input-field pl-9"
                autoComplete="off"
              />
            </div>
          </div>
          <div className="flex-1">
            <label htmlFor="location" className="label">Location</label>
            <div className="relative mt-1.5">
              <MapPin size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-mute" />
              <input
                id="location"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                placeholder="Palawan"
                className="input-field pl-9"
                autoComplete="off"
              />
            </div>
          </div>
          <Button type="submit" disabled={running} className="lg:mb-px">
            {running ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />}
            <span className="ml-2">{running ? 'Searching…' : 'Find leads'}</span>
          </Button>
        </form>

        <p className="mt-3 text-xs text-ink-mute">
          The worker runs this in the background. Results below refresh when it finishes.
        </p>

        {job && (
          <div className="mt-4 flex flex-wrap items-center gap-2 rounded-xl bg-ink/[0.03] px-3 py-2 text-xs text-ink-soft">
            <Badge variant={job.status === 'failed' ? 'error' : job.status === 'succeeded' ? 'success' : 'info'}>
              {job.status}
            </Badge>
            <span className="font-mono text-[11px] text-ink-mute">job {job.id.slice(0, 8)}</span>
            {job.result && <span>{job.result.created ?? 0} leads saved</span>}
            {job.error && <span className="text-error-600 dark:text-error-400">{job.error}</span>}
          </div>
        )}
      </section>

      {/* Leads */}
      <section className="card overflow-hidden">
        <div className="flex items-center justify-between border-b px-5 py-4">
          <h2 className="flex items-center gap-2 font-display text-[15px] font-semibold tracking-[-0.01em] text-ink">
            <Users size={16} className="text-ink-mute" />
            Leads
          </h2>
          <span className="font-mono text-[11.5px] uppercase tracking-[0.1em] text-ink-mute">
            {leads.length} total
          </span>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <LoadingSpinner />
          </div>
        ) : leads.length === 0 ? (
          <div className="px-5 py-16 text-center">
            <p className="font-display text-[1.05rem] font-semibold text-ink">No leads yet</p>
            <p className="mx-auto mt-1.5 max-w-sm text-sm text-ink-mute">
              Run a search above — the worker stores every business it finds here.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead>
                <tr className="border-b font-mono text-[11px] uppercase tracking-[0.1em] text-ink-mute">
                  <th className="px-5 py-3 font-medium">Business</th>
                  <th className="px-5 py-3 font-medium">Email</th>
                  <th className="px-5 py-3 font-medium">Phone</th>
                  <th className="px-5 py-3 font-medium">Status</th>
                  <th className="px-5 py-3 font-medium">Source</th>
                </tr>
              </thead>
              <tbody>
                {leads.map((lead) => (
                  <tr key={lead.id} className="border-b last:border-0 hover:bg-ink/[0.02]">
                    <td className="px-5 py-3.5">
                      <span className="font-medium text-ink">{lead.businessName}</span>
                      {(lead.niche || lead.location) && (
                        <span className="mt-0.5 block text-xs text-ink-mute">
                          {[lead.niche, lead.location].filter(Boolean).join(' · ')}
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-3.5">
                      {lead.email ? (
                        <a href={`mailto:${lead.email}`} className="inline-flex items-center gap-1.5 text-ink-soft hover:text-accent">
                          <Mail size={13} className="text-ink-mute" />
                          {lead.email}
                        </a>
                      ) : (
                        <span className="text-ink-mute">—</span>
                      )}
                    </td>
                    <td className="px-5 py-3.5">
                      {lead.phone ? (
                        <a href={`tel:${lead.phone.replace(/\s+/g, '')}`} className="inline-flex items-center gap-1.5 text-ink-soft hover:text-accent">
                          <Phone size={13} className="text-ink-mute" />
                          {lead.phone}
                        </a>
                      ) : (
                        <span className="text-ink-mute">—</span>
                      )}
                    </td>
                    <td className="px-5 py-3.5">
                      <Badge variant={STATUS_VARIANT[lead.status] ?? 'gray'}>{lead.status}</Badge>
                    </td>
                    <td className="px-5 py-3.5 text-xs uppercase tracking-[0.08em] text-ink-mute">
                      {lead.source ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
