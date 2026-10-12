import type { Metadata } from "next";
import { Suspense } from "react";
import { ResetPasswordForm } from "@/components/account/PasswordReset";

export const metadata: Metadata = { title: "Choose a new password" };

export default function ResetPasswordPage() {
  // (The form reads ?token= from the URL, which is only known at request time.)
  return (
    <Suspense>
      <ResetPasswordForm />
    </Suspense>
  );
}
