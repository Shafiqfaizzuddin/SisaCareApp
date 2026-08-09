import {
  AlertTriangle,
  Award,
  Camera,
  Check,
  FileImage,
  Info,
  LocateFixed,
  MapPin,
  ShieldCheck,
  UserRound,
} from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { PageIntro } from '../components/common/PageIntro'
import { useRole } from '../features/authentication/useRole'
import { wasteCategoryOptions } from '../features/reporting/categories'
import {
  getRewardRulePoints,
  submitReport,
} from '../features/reporting/report-api'
import type { WasteCategory } from '../types'

export function SubmitReportPage() {
  const navigate = useNavigate()
  const { role, user, refreshProfile } = useRole()
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [category, setCategory] = useState<WasteCategory>('household')
  const [locationAddress, setLocationAddress] = useState('')
  const [coordinates, setCoordinates] = useState<{
    latitude: number
    longitude: number
  } | null>(null)
  const [locating, setLocating] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const rewardRules = useQuery({
    queryKey: ['reward-rules'],
    queryFn: getRewardRulePoints,
  })
  const isMember = role === 'user' && Boolean(user)

  function captureLocation() {
    if (!navigator.geolocation) {
      setError('Location services are not available in this browser.')
      return
    }

    setLocating(true)
    setError(null)
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setCoordinates({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
        })
        setLocating(false)
      },
      () => {
        setError('Location access was unavailable. You can still enter the address manually.')
        setLocating(false)
      },
      { enableHighAccuracy: true, timeout: 10_000 },
    )
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedFile) {
      setError('Choose a waste photo before submitting.')
      return
    }

    const form = new FormData(event.currentTarget)
    setSubmitting(true)
    setError(null)

    try {
      const result = await submitReport({
        file: selectedFile,
        userId: isMember ? user?.id : undefined,
        guestName: isMember ? undefined : String(form.get('reporterName') ?? ''),
        guestEmail: isMember ? undefined : String(form.get('reporterEmail') ?? ''),
        description: String(form.get('description') ?? ''),
        locationAddress,
        category,
        latitude: coordinates?.latitude,
        longitude: coordinates?.longitude,
      })

      if (isMember) await refreshProfile()

      navigate('/report/success', {
        state: {
          reference: result.reference,
          submittedAt: result.submittedAt,
          awardedPoints: result.awardedPoints,
          validationBonus: rewardRules.data?.validation ?? 0,
          isMember,
        },
      })
    } catch (submissionError) {
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : 'The report could not be submitted. Please try again.',
      )
      setSubmitting(false)
    }
  }

  if (role === 'admin') {
    return (
      <section className="section">
        <div className="container empty-state empty-state--page">
          <h1>Administrator account active</h1>
          <p>Public reports can be submitted while signed out or from a member account.</p>
          <Link className="button button--primary" to="/admin">Return to admin workspace</Link>
        </div>
      </section>
    )
  }

  return (
    <section className="section report-page">
      <div className="container">
        <PageIntro
          eyebrow={isMember ? 'Member report' : 'Guest report'}
          title="Report illegal dumping"
          description="Share a clear image and location. Avoid touching unknown waste or entering unsafe areas."
        />

        <div className="report-layout">
          <form className="report-form" onSubmit={handleSubmit}>
            <section className="form-section reporter-section">
              <div className="form-section__heading">
                <span><UserRound size={16} /></span>
                <div>
                  <h2>Reporter information</h2>
                  <p>
                    {isMember
                      ? 'Your registered account details are included automatically.'
                      : 'We need your name and email so the report can be followed up.'}
                  </p>
                </div>
              </div>
              {isMember && user ? (
                <div className="member-identity">
                  <span className="member-identity__avatar">
                    {user.name.split(' ').map((part) => part[0]).join('')}
                  </span>
                  <div>
                    <strong>{user.name}</strong>
                    <span>{user.email}</span>
                  </div>
                  <span className="member-identity__verified">
                    <Check size={15} /> Registered member
                  </span>
                </div>
              ) : (
                <div className="guest-fields">
                  <div className="field">
                    <label htmlFor="reporter-name">Full name</label>
                    <input id="reporter-name" name="reporterName" autoComplete="name" placeholder="Enter your full name" required />
                  </div>
                  <div className="field">
                    <label htmlFor="reporter-email">Email address</label>
                    <input id="reporter-email" name="reporterEmail" type="email" autoComplete="email" placeholder="name@example.com" required />
                  </div>
                </div>
              )}
            </section>

            <section className="form-section">
              <div className="form-section__heading">
                <span>1</span>
                <div>
                  <h2>Add a photo</h2>
                  <p>Use a clear image that shows the waste and its surroundings.</p>
                </div>
              </div>
              <label className="upload-field">
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  required
                  onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
                />
                <span className="upload-field__icon">
                  {selectedFile ? <FileImage size={25} /> : <Camera size={25} />}
                </span>
                <strong>{selectedFile?.name || 'Choose a waste photo'}</strong>
                <span>{selectedFile ? 'Photo selected. Choose another file to replace it.' : 'JPG, PNG, or WEBP up to 10 MB'}</span>
              </label>
            </section>

            <section className="form-section">
              <div className="form-section__heading">
                <span>2</span>
                <div>
                  <h2>Describe the location</h2>
                  <p>Add enough detail for a response team to find the site.</p>
                </div>
              </div>
              <div className="field">
                <div className="field__label-row">
                  <label htmlFor="location">Address or nearby landmark</label>
                  <button type="button" onClick={captureLocation} disabled={locating}>
                    <LocateFixed size={14} /> {locating ? 'Locating...' : 'Use current location'}
                  </button>
                </div>
                <div className="input-with-icon">
                  <MapPin size={18} />
                  <input
                    id="location"
                    name="location"
                    placeholder="e.g. Jalan Tasik Selatan 8, near the service road"
                    value={locationAddress}
                    onChange={(event) => setLocationAddress(event.target.value)}
                    required
                  />
                </div>
                {coordinates && <span className="field__hint">GPS coordinates attached to this report.</span>}
              </div>
              <div className="field">
                <label htmlFor="description">What can you see?</label>
                <textarea id="description" name="description" rows={4} placeholder="Describe the amount of waste, nearby hazards, or anything blocking access." />
                <span className="field__hint">Do not include sensitive personal information.</span>
              </div>
            </section>

            <section className="form-section">
              <div className="form-section__heading">
                <span>3</span>
                <div>
                  <h2>Choose a waste category</h2>
                  <p>Select the closest match. AI analysis can confirm or adjust it later.</p>
                </div>
              </div>
              <div className="category-options">
                {wasteCategoryOptions.map((option) => (
                  <label className={`category-option ${category === option.value ? 'category-option--selected' : ''}`} key={option.value}>
                    <input type="radio" name="category" value={option.value} checked={category === option.value} onChange={() => setCategory(option.value)} />
                    <span className="category-option__check"><Check size={14} /></span>
                    <span><strong>{option.label}</strong><small>{option.description}</small></span>
                  </label>
                ))}
              </div>
              <label className="checkbox-field">
                <input type="checkbox" required />
                <span>I confirm this report is accurate to the best of my knowledge.</span>
              </label>
            </section>

            {error && <p className="form-error" role="alert">{error}</p>}
            <div className="form-actions">
              <p><ShieldCheck size={17} /> Your report is shared only with authorised response teams.</p>
              <button className="button button--primary" type="submit" disabled={submitting}>
                {submitting ? 'Submitting...' : isMember ? 'Submit and earn points' : 'Submit report'}
                <Check size={17} />
              </button>
            </div>
          </form>

          <aside className="report-guidance">
            <div className="guidance-block guidance-block--warning">
              <AlertTriangle size={21} />
              <div><h2>Stay at a safe distance</h2><p>Do not touch chemicals, sharp objects, smoke, or unknown containers. Contact emergency services for immediate danger.</p></div>
            </div>
            <div className="guidance-block">
              <Info size={21} />
              <div><h2>A useful photo includes</h2><ul><li>The full waste pile</li><li>A nearby landmark or road</li><li>Any access obstruction</li></ul></div>
            </div>
            {isMember && (
              <div className="guidance-block guidance-block--reward">
                <Award size={21} />
                <div>
                  <h2>Member reward</h2>
                  <p>
                    Earn {rewardRules.data?.submission ?? 0} points when received and {rewardRules.data?.validation ?? 0} more after an administrator confirms the report is valid.
                  </p>
                </div>
              </div>
            )}
          </aside>
        </div>
      </div>
    </section>
  )
}
