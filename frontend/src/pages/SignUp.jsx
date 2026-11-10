import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { supabase } from "../lib/supabase";
import { getAuthErrorMessage, validateEmail } from "../auth/authErrors";
import AuthLayout from "../components/AuthLayout";
import TextField from "../components/TextField";

const MIN_PASSWORD_LENGTH = 6;

function validate({ name, email, password, confirmPassword }) {
  const errors = {};
  if (!name.trim()) errors.name = "Enter your full name.";
  const emailError = validateEmail(email);
  if (emailError) errors.email = emailError;
  if (!password) {
    errors.password = "Create a password.";
  } else if (password.length < MIN_PASSWORD_LENGTH) {
    errors.password = `Use at least ${MIN_PASSWORD_LENGTH} characters.`;
  }
  if (!confirmPassword) {
    errors.confirmPassword = "Re-enter your password.";
  } else if (password && confirmPassword !== password) {
    errors.confirmPassword = "Passwords do not match.";
  }
  return errors;
}

const FIELD_IDS = {
  name: "sign-up-name",
  email: "sign-up-email",
  password: "sign-up-password",
  confirmPassword: "sign-up-confirm-password",
};

export default function SignUp() {
  const [values, setValues] = useState({
    name: "",
    email: "",
    password: "",
    confirmPassword: "",
  });
  const [fieldErrors, setFieldErrors] = useState({});
  const [formError, setFormError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [confirmationEmail, setConfirmationEmail] = useState("");
  const isSubmittingRef = useRef(false);

  function handleChange(event) {
    const { name, value } = event.target;
    setValues((current) => ({ ...current, [name]: value }));
    setFieldErrors((current) => ({ ...current, [name]: undefined }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (isSubmittingRef.current) return;

    const errors = validate(values);
    setFieldErrors(errors);
    setFormError("");
    const firstInvalid = Object.keys(errors)[0];
    if (firstInvalid) {
      document.getElementById(FIELD_IDS[firstInvalid])?.focus();
      return;
    }

    const email = values.email.trim();
    isSubmittingRef.current = true;
    setIsSubmitting(true);
    try {
      // The database trigger creates the public.users profile with the peer_educator role.
      const { data, error } = await supabase.auth.signUp({
        email,
        password: values.password,
        options: {
          data: { name: values.name.trim() },
        },
      });
      if (error) {
        setFormError(getAuthErrorMessage(error));
      } else if (!data.session) {
        setConfirmationEmail(email);
      }
      // With a session, the auth listener signs the user in and the router redirects.
    } catch (error) {
      setFormError(getAuthErrorMessage(error));
    } finally {
      isSubmittingRef.current = false;
      setIsSubmitting(false);
    }
  }

  if (confirmationEmail) {
    return (
      <AuthLayout
        title="Check your email to confirm your account"
        subtitle={
          <>
            We sent a confirmation link to <strong>{confirmationEmail}</strong>.
            Open it to activate your account, then sign in.
          </>
        }
        footer={
          <>
            Already confirmed? <Link to="/sign-in">Sign in</Link>
          </>
        }
      >
        <p className="form-note" role="status">
          Didn&apos;t get it? Check your spam folder, or wait a few minutes
          before trying again.
        </p>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Sign Up"
      footer={
        <>
          Already have an account? <Link to="/sign-in">Sign in</Link>
        </>
      }
    >
      <form
        className="auth-form"
        onSubmit={handleSubmit}
        noValidate
        aria-busy={isSubmitting}
      >
        <TextField
          id={FIELD_IDS.name}
          name="name"
          label="Full name"
          autoComplete="name"
          placeholder="Alex Morgan"
          value={values.name}
          onChange={handleChange}
          error={fieldErrors.name}
          required
        />
        <TextField
          id={FIELD_IDS.email}
          name="email"
          label="Email"
          type="email"
          autoComplete="email"
          placeholder="you@example.com"
          value={values.email}
          onChange={handleChange}
          error={fieldErrors.email}
          required
        />
        <TextField
          id={FIELD_IDS.password}
          name="password"
          label="Password"
          type="password"
          autoComplete="new-password"
          placeholder={`At least ${MIN_PASSWORD_LENGTH} characters`}
          value={values.password}
          onChange={handleChange}
          error={fieldErrors.password}
          required
        />
        <TextField
          id={FIELD_IDS.confirmPassword}
          name="confirmPassword"
          label="Confirm password"
          type="password"
          autoComplete="new-password"
          placeholder="Re-enter your password"
          value={values.confirmPassword}
          onChange={handleChange}
          error={fieldErrors.confirmPassword}
          required
        />

        <div className="form-alert" role="alert">
          {formError}
        </div>

        <button
          type="submit"
          className="button-primary"
          disabled={isSubmitting}
        >
          {isSubmitting && <span className="spinner" aria-hidden="true" />}
          {isSubmitting ? "Creating account…" : "Sign up"}
        </button>
      </form>
    </AuthLayout>
  );
}
