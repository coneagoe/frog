import { AuthForm } from "@/features/auth/auth-form";

export default async function ResetPasswordPage({ searchParams }: { searchParams?: Promise<{ token?: string }> }) {
  const params = await searchParams;
  return <div className="auth-page"><AuthForm mode="reset-password" token={params?.token} /></div>;
}
