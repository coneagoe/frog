import { AuthForm } from "@/features/auth/auth-form";

export default async function LoginPage({ searchParams }: { searchParams?: Promise<{ return_to?: string }> }) {
  const params = await searchParams;
  return <div className="auth-page"><AuthForm mode="login" returnTo={params?.return_to} /></div>;
}
