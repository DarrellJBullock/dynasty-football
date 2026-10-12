import type { Metadata } from "next";
import { ForgotPasswordForm } from "@/components/account/PasswordReset";

export const metadata: Metadata = { title: "Reset your password" };

export default function ForgotPasswordPage() {
  return <ForgotPasswordForm />;
}
