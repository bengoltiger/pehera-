/**
 * Framer Motion helpers. Kept deliberately small: page transitions, staggered
 * entrances and animated bars. MotionConfig reducedMotion="user" (App.tsx)
 * disables all of this for users who ask for it.
 */
import { motion, type Variants } from 'framer-motion'
import type { ReactNode } from 'react'

export const pageVariants: Variants = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.18, ease: 'easeOut' } },
  exit: { opacity: 0, y: -6, transition: { duration: 0.12, ease: 'easeIn' } },
}

export function Page({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <motion.div variants={pageVariants} initial="initial" animate="animate" exit="exit" className={className}>
      {children}
    </motion.div>
  )
}

const staggerVariants: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.045, delayChildren: 0.05 } },
}

const riseVariants: Variants = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0, transition: { duration: 0.28, ease: 'easeOut' } },
}

/** Wraps a list of <Rise> children so they enter as a staggered sequence. */
export function Stagger({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <motion.div variants={staggerVariants} initial="hidden" animate="show" className={className}>
      {children}
    </motion.div>
  )
}

export function Rise({ children, className, delay = 0 }: { children: ReactNode; className?: string; delay?: number }) {
  return (
    <motion.div
      variants={riseVariants}
      className={className}
      style={delay ? { transitionDelay: `${delay}s` } : undefined}
    >
      {children}
    </motion.div>
  )
}
