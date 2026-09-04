import { VerifyEmailPanel } from "@/features/auth/verify-email-panel";

export default async function VerifyEmailPage({ searchParams }: { searchParams?: Promise<{ token?: string }> }) {
  return <VerifyEmailPanel token={(await searchParams)?.token} />;
}
