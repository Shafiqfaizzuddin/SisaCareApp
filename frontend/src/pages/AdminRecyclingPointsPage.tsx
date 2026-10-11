import { useEffect, useState, type FormEvent } from 'react'
import { fetchAdminRecyclingPoints, saveRecyclingPoint, type RecyclingPoint } from '../features/reporting/recycling-points'
import { LocationPicker } from '../components/location/LocationPicker'
import { GoogleMap } from '../components/location/GoogleMap'
import type { ReportLocation } from '../types'

type FormState = { name: string; materials: string; description: string; accessNotes: string; openingHours: string; active: boolean }
const emptyForm: FormState = { name: '', materials: '', description: '', accessNotes: '', openingHours: '', active: true }

function fromPoint(point: RecyclingPoint): FormState {
  return { name: point.name, materials: point.accepted_materials.join(', '), description: point.description,
    accessNotes: point.access_notes ?? '', openingHours: point.opening_hours ?? '', active: point.active !== false }
}

export function AdminRecyclingPointsPage() {
  const [points, setPoints] = useState<RecyclingPoint[]>([])
  const [form, setForm] = useState<FormState>(emptyForm)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [pin, setPin] = useState<ReportLocation | null>(null)
  const [pinConfirmed, setPinConfirmed] = useState(false)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  useEffect(() => {
    let active = true
    void fetchAdminRecyclingPoints().then(result => { if (active) setPoints(result) })
      .catch(value => { if (active) setError(value instanceof Error ? value.message : 'Could not load points.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  function edit(point: RecyclingPoint) {
    setEditingId(point.id)
    setForm(fromPoint(point))
    setPin({ latitude: point.latitude, longitude: point.longitude, address: point.address || `${point.latitude}, ${point.longitude}`,
      addressSource: point.address_source ?? 'coordinates', source: 'map', street: null, city: null,
      state: null, postcode: null, country: null })
    setPinConfirmed(true)
    setError('')
    setNotice('')
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    const acceptedMaterials = [...new Map(form.materials.split(',').map(value => value.trim()).filter(Boolean)
      .map(value => [value.toLocaleLowerCase(), value])).values()]
    if (!form.name.trim() || acceptedMaterials.length === 0 || !pin || !pinConfirmed) {
      setError('Enter a name and accepted materials, then confirm the station pin.')
      return
    }
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const saved = await saveRecyclingPoint({
        name: form.name.trim(), latitude: pin.latitude, longitude: pin.longitude,
        address: pin.address, address_source: pin.addressSource ?? null,
        accepted_materials: acceptedMaterials, description: form.description.trim(),
        access_notes: form.accessNotes.trim(), opening_hours: form.openingHours.trim(), active: form.active,
      }, editingId ?? undefined)
      setPoints(current => [...current.filter(point => point.id !== saved.id), saved]
        .sort((a, b) => a.name.localeCompare(b.name)))
      setNotice(editingId ? 'Recycling point updated.' : 'Recycling point registered.')
      setForm(emptyForm)
      setPin(null)
      setPinConfirmed(false)
      setEditingId(null)
    } catch (value) {
      setError(value instanceof Error ? value.message : 'The point could not be saved.')
    } finally {
      setBusy(false)
    }
  }

  async function deactivate(point: RecyclingPoint) {
    if (busy) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const saved = await saveRecyclingPoint({ ...point, active: false }, point.id)
      setPoints(current => current.map(entry => entry.id === saved.id ? saved : entry))
      if (editingId === point.id) { setForm(emptyForm); setEditingId(null); setPin(null); setPinConfirmed(false) }
      setNotice(`${point.name} deactivated. Historical activity references remain available.`)
    } catch (value) {
      setError(value instanceof Error ? value.message : 'The point could not be deactivated.')
    } finally {
      setBusy(false)
    }
  }

  return <section className="admin-recycling-page">
    <header className="admin-page-heading"><div><p className="eyebrow">Registered locations</p><h1>Recycling points</h1><p>Register confirmed recycling locations. Only active production points are recommended for proof submissions.</p></div></header>
    {loading && <p role="status">Loading recycling points...</p>}
    {error && <p role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    <div className="admin-panel">
      <h2>{editingId ? 'Edit recycling point' : 'Register recycling point'}</h2>
      <form className="recycling-point-form" onSubmit={event => void save(event)}>
        <div className="field"><label htmlFor="point-name">Name</label><input id="point-name" value={form.name} onChange={event => setForm(current => ({ ...current, name: event.target.value }))} maxLength={160} required disabled={busy} /></div>
        <LocationPicker idPrefix="station" mapLabel="Select a recycling station pin" value={pin} confirmed={pinConfirmed}
          note={form.accessNotes} noteLabel="Access notes (optional)" onNoteChange={value => setForm(current => ({ ...current, accessNotes: value }))}
          onChange={value => { setPin(value); setPinConfirmed(false) }} onConfirm={() => setPinConfirmed(true)} />
        <div className="field"><label htmlFor="point-materials">Accepted materials</label><input id="point-materials" value={form.materials} onChange={event => setForm(current => ({ ...current, materials: event.target.value }))} placeholder="Plastic, Paper, Metal" required disabled={busy} /><span className="field__hint">Separate materials with commas. Use the same names shown in confirmed waste results.</span></div>
        <div className="field"><label htmlFor="point-description">Description</label><textarea id="point-description" value={form.description} onChange={event => setForm(current => ({ ...current, description: event.target.value }))} maxLength={2000} rows={3} disabled={busy} /></div>
        <div className="field"><label htmlFor="point-hours">Opening hours (optional)</label><input id="point-hours" value={form.openingHours} onChange={event => setForm(current => ({ ...current, openingHours: event.target.value }))} maxLength={500} disabled={busy} /></div>
        <label className="checkbox-field"><input type="checkbox" checked={form.active} onChange={event => setForm(current => ({ ...current, active: event.target.checked }))} disabled={busy} /> Active and visible to participants</label>
        <div className="recycling-point-form__actions"><button className="button button--primary" disabled={busy || !pinConfirmed}>{busy ? 'Saving...' : editingId ? 'Save changes' : 'Register point'}</button>{editingId && <button type="button" className="button button--secondary" disabled={busy} onClick={() => { setEditingId(null); setForm(emptyForm); setPin(null); setPinConfirmed(false) }}>Cancel edit</button>}</div>
      </form>
    </div>
    <div className="admin-panel"><h2>Registered points</h2>
      <GoogleMap location={pin} markers={points.map(point => ({ id: point.id, name: point.name, latitude: point.latitude, longitude: point.longitude }))}
        selectedMarkerId={editingId} onMarkerSelect={id => { const point = points.find(entry => entry.id === id); if (point) edit(point) }} ariaLabel="Map of registered recycling stations" />
      {!loading && points.length === 0 && <p>No registered recycling points have been added yet.</p>}
      <ul className="admin-recycling-list">{points.map(point => <li key={point.id}>
        <div><strong>{point.name}</strong> <span>{point.active ? 'Active' : 'Inactive'}</span><p>{point.accepted_materials.join(', ')}</p><p>{point.address || 'Address not recorded'}</p><p>{point.latitude.toFixed(6)}, {point.longitude.toFixed(6)}</p>{point.description && <p>{point.description}</p>}{point.access_notes && <p>Access: {point.access_notes}</p>}{point.opening_hours && <p>Hours: {point.opening_hours}</p>}</div>
        <div className="admin-recycling-list__actions"><button type="button" className="button button--secondary" disabled={busy} onClick={() => edit(point)}>Edit</button>{point.active && <button type="button" className="button button--secondary" disabled={busy} onClick={() => void deactivate(point)}>Deactivate</button>}</div>
      </li>)}</ul>
    </div>
  </section>
}
