/**
 * Admin frontend entrypoint.
 * Feature code lives under ./src and is composed by AdminApplication.
 * Keep this stable URL because Telegram WebApp and the API serve it directly.
 */
const assetVersion = new URL(import.meta.url).searchParams.get('v');
const appUrl = assetVersion ? `./src/app.js?v=${encodeURIComponent(assetVersion)}` : './src/app.js';
import(appUrl).catch((error) => {
  console.error('Admin application failed to load', error);
});
