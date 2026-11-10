import { useState } from 'react'

export default function TextField({ id, label, error, type = 'text', ...inputProps }) {
  const [isPasswordVisible, setIsPasswordVisible] = useState(false)
  const isPassword = type === 'password'
  const errorId = `${id}-error`

  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>
        {label}
      </label>
      <div className={isPassword ? 'field-control has-toggle' : 'field-control'}>
        <input
          id={id}
          className="field-input"
          type={isPassword && isPasswordVisible ? 'text' : type}
          aria-invalid={error ? 'true' : undefined}
          aria-describedby={error ? errorId : undefined}
          {...inputProps}
        />
        {isPassword && (
          <button
            type="button"
            className="field-toggle"
            onClick={() => setIsPasswordVisible((visible) => !visible)}
            aria-controls={id}
            aria-label={isPasswordVisible ? `Hide ${label.toLowerCase()}` : `Show ${label.toLowerCase()}`}
          >
            {isPasswordVisible ? 'Hide' : 'Show'}
          </button>
        )}
      </div>
      {error && (
        <p className="field-error" id={errorId}>
          {error}
        </p>
      )}
    </div>
  )
}
