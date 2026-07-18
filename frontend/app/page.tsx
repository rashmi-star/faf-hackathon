import { LandingPage } from '@/components/landing/landing-page';

/*
 * STUDIO-BUILDER MARKER: this route is now the cinematic landing page.
 * The LiveKit session UI that used to render here (`<App appConfig={...} />`
 * from '@/components/app/app', configured via `getAppConfig(await headers())`)
 * was NOT moved or modified — mount it at app/studio/page.tsx. The landing
 * CTAs link to /studio.
 */
export default function Page() {
  return <LandingPage />;
}
