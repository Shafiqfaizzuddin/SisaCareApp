import {
  AlertTriangle,
  Award,
  Camera,
  Check,
  FileImage,
  Info,
  MapPin,
  ShieldCheck,
  UserRound,
} from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { PageIntro } from '../components/common/PageIntro'
import { useRole } from '../features/authentication/useRole'
import { wasteCategoryOptions } from '../features/reporting/categories'
import type { WasteCategory } from '../types'

export function SubmitReportPage() {
  const navigate = useNavigate()
  const { role, user, rewardMember } = useRole()
  const [selectedFile, setSelectedFile] = useState('')
  const [category, setCategory] = useState<WasteCategory>('household')

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (role === 'user') {
      rewardMember(10)
    }
    navigate('/report/success', {
      state: {
        reference: 'SCA-1051',
        isMember: role === 'user',
      },
    })
  }

  return (
    <section className="section report-page">
      <div className="container">
        <PageIntro
          eyebrow={role === 'user' ? 'Member report' : 'Guest report'}
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
                    {role === 'user'
                      ? 'Your registered account details are included automatically.'
                      : 'We need your name and email so the report can be followed up.'}
                  </p>
                </div>
              </div>
              {role === 'user' && user ? (
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
                    <input
                      id="reporter-name"
                      name="reporterName"
                      autoComplete="name"
                      placeholder="Enter your full name"
                      required
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="reporter-email">Email address</label>
                    <input
                      id="reporter-email"
                      name="reporterEmail"
                      type="email"
                      autoComplete="email"
                      placeholder="name@example.com"
                      required
                    />
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
                  onChange={(event) =>
                    setSelectedFile(event.target.files?.[0]?.name ?? '')
                  }
                />
                <span className="upload-field__icon">
                  {selectedFile ? <FileImage size={25} /> : <Camera size={25} />}
                </span>
                <strong>{selectedFile || 'Choose a waste photo'}</strong>
                <span>
                  {selectedFile
                    ? 'Photo selected. Choose another file to replace it.'
                    : 'JPG, PNG, or WEBP up to 10 MB'}
                </span>
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
                <label htmlFor="location">Address or nearby landmark</label>
                <div className="input-with-icon">
                  <MapPin size={18} />
                  <input
                    id="location"
                    name="location"
                    placeholder="e.g. Jalan Tasik Selatan 8, near the service road"
                    required
                  />
                </div>
              </div>
              <div className="field">
                <label htmlFor="description">What can you see?</label>
                <textarea
                  id="description"
                  name="description"
                  rows={4}
                  placeholder="Describe the amount of waste, nearby hazards, or anything blocking access."
                  required
                />
                <span className="field__hint">Do not include sensitive personal information.</span>
              </div>
            </section>

            <section className="form-section">
              <div className="form-section__heading">
                <span>3</span>
                <div>
                  <h2>Choose a waste category</h2>
                  <p>Select the closest match. The report can be reviewed later.</p>
                </div>
              </div>
              <div className="category-options">
                {wasteCategoryOptions.map((option) => (
                  <label
                    className={`category-option ${
                      category === option.value ? 'category-option--selected' : ''
                    }`}
                    key={option.value}
                  >
                    <input
                      type="radio"
                      name="category"
                      value={option.value}
                      checked={category === option.value}
                      onChange={() => setCategory(option.value)}
                    />
                    <span className="category-option__check">
                      <Check size={14} />
                    </span>
                    <span>
                      <strong>{option.label}</strong>
                      <small>{option.description}</small>
                    </span>
                  </label>
                ))}
              </div>
              <label className="checkbox-field">
                <input type="checkbox" required />
                <span>
                  I confirm this report is accurate to the best of my knowledge.
                </span>
              </label>
            </section>

            <div className="form-actions">
              <p>
                <ShieldCheck size={17} />
                Your report is shared only with authorised response teams.
              </p>
              <button className="button button--primary" type="submit">
                {role === 'user' ? 'Submit and earn points' : 'Submit report'}
                <Check size={17} />
              </button>
            </div>
          </form>

          <aside className="report-guidance">
            <div className="guidance-block guidance-block--warning">
              <AlertTriangle size={21} />
              <div>
                <h2>Stay at a safe distance</h2>
                <p>
                  Do not touch chemicals, sharp objects, smoke, or unknown
                  containers. Contact emergency services for immediate danger.
                </p>
              </div>
            </div>
            <div className="guidance-block">
              <Info size={21} />
              <div>
                <h2>A useful photo includes</h2>
                <ul>
                  <li>The full waste pile</li>
                  <li>A nearby landmark or road</li>
                  <li>Any access obstruction</li>
                </ul>
              </div>
            </div>
            {role === 'user' && (
              <div className="guidance-block guidance-block--reward">
                <Award size={21} />
                <div>
                  <h2>Member reward</h2>
                  <p>
                    Earn 10 points when received and up to 40 bonus points after
                    an administrator confirms the report is valid.
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
