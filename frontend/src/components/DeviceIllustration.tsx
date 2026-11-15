import React from 'react';

interface DeviceIllustrationProps {
  type: string;
  className?: string;
}

/**
 * Clean monochrome-blue vector hardware schematic matching DESIGN.md obsidian aesthetic.
 * Keys match backend/hardware_devices.py HARDWARE_CATALOG[*]["illustration_type"] 1:1.
 */
export const DeviceIllustration: React.FC<DeviceIllustrationProps> = ({
  type,
  className = 'w-14 h-14',
}) => {
  const stroke = '#A5D8FF';
  const muted = 'rgba(229,229,228,0.45)';
  const fillBg = '#181C2E';

  const renderArtwork = () => {
    switch (type) {
      case 'actigraphy_watch':
        return (
          <>
            <rect x="23" y="8" width="18" height="10" rx="2" stroke={muted} strokeWidth="2" />
            <rect x="19" y="18" width="26" height="28" rx="6" fill={fillBg} stroke={stroke} strokeWidth="2" />
            <rect x="23" y="46" width="18" height="10" rx="2" stroke={muted} strokeWidth="2" />
            <path d="M24 34l4-6 4 9 4-11 4 8" stroke={stroke} strokeWidth="2" />
          </>
        );
      case 'smart_shirt':
        return (
          <>
            <path
              d="M20 14l7-4h10l7 4 9 7-5 8-5-3v24H21V26l-5 3-5-8 9-7z"
              fill={fillBg}
              stroke={stroke}
              strokeWidth="2"
            />
            <path d="M25 32h4l2-5 3 10 3-5h4" stroke={stroke} strokeWidth="2" />
            <circle cx="38" cy="24" r="2.2" fill={stroke} />
          </>
        );
      case 'bp_cuff':
        return (
          <>
            <rect x="14" y="16" width="22" height="32" rx="4" fill={fillBg} stroke={stroke} strokeWidth="2" />
            <path d="M36 30h8a6 6 0 0 1 6 6v4" stroke={muted} strokeWidth="2" />
            <circle cx="50" cy="45" r="5" stroke={stroke} strokeWidth="2" />
            <path d="M18 26h14M18 34h10" stroke={stroke} strokeWidth="2" />
          </>
        );
      case 'thigh_cuffs':
        return (
          <>
            <rect x="14" y="18" width="15" height="28" rx="4" stroke={stroke} strokeWidth="2" />
            <rect x="35" y="18" width="15" height="28" rx="4" stroke={stroke} strokeWidth="2" />
            <path d="M14 26h15M14 38h15M35 26h15M35 38h15" stroke={muted} strokeWidth="2" />
            <path d="M21 12v4M43 12v4" stroke={stroke} strokeWidth="2" />
          </>
        );
      case 'ultrasound_probe':
        return (
          <>
            <rect x="20" y="10" width="24" height="16" rx="3" stroke={stroke} strokeWidth="2" />
            <path d="M25 26v10c0 4 14 4 14 0V26" stroke={stroke} strokeWidth="2" />
            <path d="M22 44c6 4 14 4 20 0M18 50c9 5 19 5 28 0" stroke={muted} strokeWidth="2" />
          </>
        );
      case 'ocular_tonometer':
        return (
          <>
            <path d="M10 32s10-12 22-12 22 12 22 12-10 12-22 12-22-12-22-12z" stroke={stroke} strokeWidth="2" />
            <circle cx="32" cy="32" r="6" stroke={stroke} strokeWidth="2" />
            <circle cx="32" cy="32" r="2" fill={stroke} />
            <path d="M48 16l8-6" stroke={muted} strokeWidth="2" />
          </>
        );
      case 'mri_scanner':
        return (
          <>
            <circle cx="32" cy="30" r="18" stroke={stroke} strokeWidth="2" />
            <circle cx="32" cy="30" r="10" stroke={muted} strokeWidth="2" />
            <path d="M20 48h24M24 54h16" stroke={stroke} strokeWidth="2" />
            <rect x="28" y="34" width="8" height="14" rx="1" stroke={stroke} strokeWidth="1.5" />
          </>
        );
      case 'bone_scanner':
        return (
          <>
            <rect x="14" y="14" width="36" height="36" rx="4" stroke={muted} strokeWidth="2" />
            <path d="M32 18c-3 0-4 3-3 6l1 14c-1 3 0 6 2 6s3-3 2-6l1-14c1-3 0-6-3-6z" stroke={stroke} strokeWidth="2" />
            <path d="M20 30h6M38 30h6" stroke={stroke} strokeWidth="2" />
          </>
        );
      case 'evarm_badge':
        return (
          <>
            <rect x="18" y="12" width="28" height="40" rx="4" stroke={stroke} strokeWidth="2" />
            <circle cx="32" cy="24" r="5" stroke={stroke} strokeWidth="2" />
            <path d="M24 38h16M24 44h10" stroke={muted} strokeWidth="2" />
          </>
        );
      case 'bubble_detector':
        return (
          <>
            <rect x="23" y="10" width="18" height="44" rx="7" stroke={stroke} strokeWidth="2" />
            <circle cx="29" cy="24" r="2.2" stroke={stroke} strokeWidth="1.8" />
            <circle cx="35" cy="32" r="2.6" stroke={stroke} strokeWidth="1.8" />
            <circle cx="30" cy="40" r="1.8" stroke={stroke} strokeWidth="1.8" />
          </>
        );
      case 'bubble_reader':
        return (
          <>
            <rect x="12" y="18" width="40" height="30" rx="4" stroke={stroke} strokeWidth="2" />
            <rect x="18" y="24" width="16" height="18" rx="2" stroke={muted} strokeWidth="2" />
            <circle cx="43" cy="28" r="3" stroke={stroke} strokeWidth="2" />
            <path d="M39 38h8" stroke={stroke} strokeWidth="2" />
          </>
        );
      case 'cans_spectrometer':
        return (
          <>
            <polygon points="32,10 50,20 50,44 32,54 14,44 14,20" stroke={stroke} strokeWidth="2" />
            <path d="M22 36l6-8 5 6 7-10 4 6" stroke={stroke} strokeWidth="2" />
          </>
        );
      case 'tempus_pro':
        return (
          <>
            <rect x="10" y="14" width="44" height="34" rx="4" stroke={stroke} strokeWidth="2" />
            <rect x="16" y="20" width="22" height="18" rx="2" stroke={muted} strokeWidth="2" />
            <path d="M18 30h4l2-5 3 9 2-4h5" stroke={stroke} strokeWidth="2" />
            <circle cx="46" cy="24" r="2" fill={stroke} />
            <circle cx="46" cy="33" r="2" fill={muted} />
          </>
        );
      case 'ai_platform':
        return (
          <>
            <circle cx="32" cy="32" r="16" stroke={muted} strokeWidth="2" />
            <path d="M20 42L32 16l12 26" stroke={stroke} strokeWidth="2" />
            <path d="M24 34h16" stroke={stroke} strokeWidth="2" />
          </>
        );
      case 'saliva_booklet':
        return (
          <>
            <rect x="14" y="14" width="18" height="36" rx="2" stroke={stroke} strokeWidth="2" />
            <rect x="32" y="14" width="18" height="36" rx="2" stroke={muted} strokeWidth="2" />
            <circle cx="41" cy="25" r="3" stroke={stroke} strokeWidth="1.8" />
            <circle cx="41" cy="36" r="3" stroke={stroke} strokeWidth="1.8" />
          </>
        );
      case 'biosample_kit':
        return (
          <>
            <path d="M20 14h8v28a4 4 0 0 1-8 0V14z" stroke={stroke} strokeWidth="2" />
            <path d="M36 14h8v28a4 4 0 0 1-8 0V14z" stroke={stroke} strokeWidth="2" />
            <path d="M16 14h32M14 50h36" stroke={muted} strokeWidth="2" />
          </>
        );
      case 'behavioral_survey':
        return (
          <>
            <rect x="16" y="12" width="32" height="40" rx="3" stroke={stroke} strokeWidth="2" />
            <path d="M24 24h16M24 32h16M24 40h10" stroke={muted} strokeWidth="2" />
            <path d="M26 12v-2h12v2" stroke={stroke} strokeWidth="2" />
          </>
        );
      case 'balance_plate':
        return (
          <>
            <circle cx="32" cy="18" r="4" stroke={stroke} strokeWidth="2" />
            <path d="M32 22v16M22 28h20M26 44l6-6 6 6" stroke={stroke} strokeWidth="2" />
            <rect x="14" y="48" width="36" height="6" rx="2" stroke={muted} strokeWidth="2" />
          </>
        );
      case 'cycle_ergometer':
        return (
          <>
            <circle cx="22" cy="40" r="9" stroke={stroke} strokeWidth="2" />
            <circle cx="44" cy="40" r="6" stroke={muted} strokeWidth="2" />
            <path d="M22 40l10-16h10l2 16M28 18h10" stroke={stroke} strokeWidth="2" />
          </>
        );
      case 'veggie_garden':
        return (
          <>
            <rect x="14" y="14" width="36" height="38" rx="4" stroke={muted} strokeWidth="2" />
            <path d="M32 44V28M32 34c-6-1-9-5-8-10 5 1 8 4 8 10zM32 32c6-1 9-5 8-10-5 1-8 4-8 10z" stroke={stroke} strokeWidth="2" />
            <path d="M20 44h24" stroke={stroke} strokeWidth="2" />
          </>
        );
      default:
        return (
          <>
            <rect x="16" y="16" width="32" height="32" rx="6" stroke={stroke} strokeWidth="2" />
            <path d="M22 32h5l3-7 4 14 3-7h5" stroke={stroke} strokeWidth="2" />
          </>
        );
    }
  };

  return (
    <div
      className={`rounded-xl border border-white/10 bg-[#181C2E] flex items-center justify-center shrink-0 ${className}`}
      aria-hidden="true"
    >
      <svg viewBox="0 0 64 64" className="w-10 h-10" fill="none" strokeLinecap="round" strokeLinejoin="round">
        {renderArtwork()}
      </svg>
    </div>
  );
};
