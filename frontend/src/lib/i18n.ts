/**
 * Bilingual UI strings (Section 33).
 *
 * Only UI chrome lives here. Risk explanations, alert copy and narratives come
 * from the backend in the requested language, because the engine owns the
 * wording just as it owns the numbers.
 */
import { createContext, useContext } from 'react'
import type { Lang } from './types'

type Dict = Record<string, string>

export const STRINGS: Record<Lang, Dict> = {
  en: {
    'app.name': 'PEHRA',
    'app.tagline': 'Predictive Early-warning for Hyperlocal Risk Assessment',
    'app.demoBanner': 'DEMO / SIMULATED DATA',
    'app.demoBannerDetail':
      'All environmental values are produced by deterministic simulation. No live weather, satellite, river or notification service is connected.',

    'nav.overview': 'Overview',
    'nav.sitrep': 'SITREP',
    'nav.predict': 'Predict',
    'nav.map': 'Map',
    'nav.queue': 'Priority queue',
    'nav.alerts': 'Alerts',
    'nav.incidents': 'Incidents',
    'nav.analytics': 'Analytics',
    'nav.lab': 'Simulation lab',
    'nav.replay': 'Replay',
    'nav.whatif': 'What-if',
    'nav.system': 'System',
    'nav.audit': 'Audit log',
    'nav.citizen': 'Citizen view',
    'nav.authority': 'Command centre',
    'nav.judge': 'Judge demo',

    'action.signIn': 'Sign in',
    'action.signOut': 'Sign out',
    'action.retry': 'Retry',
    'action.refresh': 'Refresh',
    'action.close': 'Close',
    'action.cancel': 'Cancel',
    'action.save': 'Save',
    'action.approve': 'Approve & issue',
    'action.preview': 'Preview',
    'action.acknowledge': 'I understand',
    'action.resetDemo': 'RESET DEMO',
    'action.step': 'Advance 15 min',
    'action.viewDetail': 'View detail',

    'label.risk': 'Risk',
    'label.hazard': 'Hazard',
    'label.exposure': 'Exposure',
    'label.confidence': 'Confidence',
    'label.momentum': 'Trend',
    'label.severity': 'Severity',
    'label.population': 'People',
    'label.priority': 'Priority',
    'label.updated': 'Updated',
    'label.source': 'Source',
    'label.simulated': 'Simulated',
    'label.dataHealth': 'Data health',
    'label.leadTime': 'Warning lead time',
    'label.peak': 'Projected peak',
    'label.decisionWindow': 'Decision window',
    'label.whyThisRisk': 'Why this risk?',
    'label.whyPriority': 'Why this priority?',
    'label.uncertainty': 'Uncertainty range',
    'label.noData': 'Not available',
    'label.loading': 'Loading…',

    'state.empty': 'Nothing to show yet.',
    'state.errorTitle': 'Something went wrong',
    'state.offline': 'Offline — showing the last values received',
    'state.degraded': 'Degraded connection — data may be older than usual',
    'state.notEnoughData': 'Not enough evaluation data',

    'risk.SAFE': 'Safe',
    'risk.LOW': 'Low',
    'risk.MODERATE': 'Moderate',
    'risk.HIGH': 'High',
    'risk.CRITICAL': 'Critical',

    'citizen.defense': 'Village Defense',
    'citizen.evacuate': 'Evacuate',
  },
  hi: {
    'app.name': 'पहरा',
    'app.tagline': 'अति-स्थानीय जोखिम आकलन हेतु पूर्वानुमान आधारित प्रारंभिक चेतावनी',
    'app.demoBanner': 'डेमो / नकली (सिम्युलेटेड) डेटा',
    'app.demoBannerDetail':
      'सभी पर्यावरणीय मान नियतात्मक सिमुलेशन से बने हैं। कोई वास्तविक मौसम, उपग्रह, नदी या सूचना सेवा जुड़ी नहीं है।',

    'nav.overview': 'सारांश',
    'nav.sitrep': 'स्थिति रिपोर्ट',
    'nav.predict': 'पूर्वानुमान',
    'nav.map': 'नक्शा',
    'nav.queue': 'प्राथमिकता सूची',
    'nav.alerts': 'चेतावनियाँ',
    'nav.incidents': 'घटनाएँ',
    'nav.analytics': 'विश्लेषण',
    'nav.lab': 'सिमुलेशन लैब',
    'nav.replay': 'रीप्ले',
    'nav.whatif': 'क्या-अगर',
    'nav.system': 'सिस्टम',
    'nav.audit': 'ऑडिट लॉग',
    'nav.citizen': 'नागरिक दृश्य',
    'nav.authority': 'कमांड सेंटर',
    'nav.judge': 'जज डेमो',

    'action.signIn': 'साइन इन',
    'action.signOut': 'साइन आउट',
    'action.retry': 'पुनः प्रयास',
    'action.refresh': 'ताज़ा करें',
    'action.close': 'बंद करें',
    'action.cancel': 'रद्द करें',
    'action.save': 'सहेजें',
    'action.approve': 'स्वीकृत कर जारी करें',
    'action.preview': 'पूर्वावलोकन',
    'action.acknowledge': 'मैं समझ गया',
    'action.resetDemo': 'डेमो रीसेट',
    'action.step': '15 मिनट आगे',
    'action.viewDetail': 'विवरण देखें',

    'label.risk': 'जोखिम',
    'label.hazard': 'खतरा',
    'label.exposure': 'जनसंपर्क',
    'label.confidence': 'विश्वास',
    'label.momentum': 'रुझान',
    'label.severity': 'गंभीरता',
    'label.population': 'लोग',
    'label.priority': 'प्राथमिकता',
    'label.updated': 'अद्यतन',
    'label.source': 'स्रोत',
    'label.simulated': 'सिम्युलेटेड',
    'label.dataHealth': 'डेटा गुणवत्ता',
    'label.leadTime': 'चेतावनी अग्रिम समय',
    'label.peak': 'अनुमानित शिखर',
    'label.decisionWindow': 'निर्णय समय',
    'label.whyThisRisk': 'यह जोखिम क्यों?',
    'label.whyPriority': 'यह प्राथमिकता क्यों?',
    'label.uncertainty': 'अनिश्चितता सीमा',
    'label.noData': 'उपलब्ध नहीं',
    'label.loading': 'लोड हो रहा है…',

    'state.empty': 'अभी दिखाने के लिए कुछ नहीं।',
    'state.errorTitle': 'कुछ गड़बड़ हुई',
    'state.offline': 'ऑफ़लाइन — अंतिम प्राप्त मान दिखाए जा रहे हैं',
    'state.degraded': 'कमज़ोर कनेक्शन — डेटा पुराना हो सकता है',
    'state.notEnoughData': 'मूल्यांकन के लिए पर्याप्त डेटा नहीं',

    'risk.SAFE': 'सुरक्षित',
    'risk.LOW': 'कम',
    'risk.MODERATE': 'मध्यम',
    'risk.HIGH': 'उच्च',
    'risk.CRITICAL': 'गंभीर',

    'citizen.defense': 'गाँव रक्षा',
    'citizen.evacuate': 'निकासी',
  },
}

export interface I18nValue {
  lang: Lang
  setLang: (l: Lang) => void
  t: (key: string, fallback?: string) => string
}

export const I18nContext = createContext<I18nValue>({
  lang: 'en',
  setLang: () => {},
  t: (k, fallback) => STRINGS.en[k] ?? fallback ?? k,
})

export function useI18n() {
  return useContext(I18nContext)
}

export function translate(lang: Lang, key: string, fallback?: string): string {
  return STRINGS[lang]?.[key] ?? STRINGS.en[key] ?? fallback ?? key
}
