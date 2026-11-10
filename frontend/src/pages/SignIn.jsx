import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { supabase } from "../lib/supabase";
import { getAuthErrorMessage, validateEmail } from "../auth/authErrors";
import AuthLayout from "../components/AuthLayout";
import TextField from "../components/TextField";

function validate({ email, password }) {
  const errors = {};
  const emailError = validateEmail(email);
  if (emailError) errors.email = emailError;
  if (!password) errors.password = "Enter your password.";
  return errors;
}

export default function SignIn() {
  const [values, setValues] = useState({ email: "", password: "" });
  const [fieldErrors, setFieldErrors] = useState({});
  const [formError, setFormError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
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
      document.getElementById(`sign-in-${firstInvalid}`)?.focus();
      return;
    }

    isSubmittingRef.current = true;
    setIsSubmitting(true);
    try {
      const { error } = await supabase.auth.signInWithPassword({
        email: values.email.trim(),
        password: values.password,
      });
      // On success the auth listener updates the session and the router redirects.
      if (error) setFormError(getAuthErrorMessage(error));
    } catch (error) {
      setFormError(getAuthErrorMessage(error));
    } finally {
      isSubmittingRef.current = false;
      setIsSubmitting(false);
    }
  }

  return (
    <AuthLayout
      title="Sign In"
      subtitle="Welcome back. Enter your email and password to sign in."
      footer={
        <>
          New to Peer Connections? <Link to="/sign-up">Create an account</Link>
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
          id="sign-in-email"
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
          id="sign-in-password"
          name="password"
          label="Password"
          type="password"
          autoComplete="current-password"
          placeholder="Your password"
          value={values.password}
          onChange={handleChange}
          error={fieldErrors.password}
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
          {isSubmitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </AuthLayout>
  );
}
