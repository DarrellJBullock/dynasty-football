import type { Metadata } from "next";
import { Suspense } from "react";
import { AuthForm } from "@/components/account/AuthForm";

export const metadata: Metadata = { title: "Sign in" };

export default function SignInPage() {
  // (The form reads ?next= from the URL, which is only known at request time.)
  return (
    <Suspense>
      <AuthForm mode="signin" />
    </Suspense>
  );
}
