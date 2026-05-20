import {
  Bell,
  EnvelopeSimple,
  SlackLogo,
  ChatCircle,
  ToggleLeft,
} from '@phosphor-icons/react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

const NOTIFICATION_CHANNELS = [
  {
    id: 'email',
    label: '이메일 알림',
    description: '인허가 변동 감지 시 등록된 이메일로 즉시 발송합니다.',
    icon: <EnvelopeSimple className="w-4 h-4 text-text-muted" weight="fill" />,
  },
  {
    id: 'slack',
    label: 'Slack 알림',
    description: 'Webhook URL을 통해 지정한 Slack 채널로 알림을 발송합니다.',
    icon: <SlackLogo className="w-4 h-4 text-text-muted" weight="fill" />,
  },
  {
    id: 'kakao',
    label: '카카오 알림톡',
    description: '카카오 비즈 채널을 통해 알림톡으로 발송합니다.',
    icon: <ChatCircle className="w-4 h-4 text-text-muted" weight="fill" />,
  },
] as const;

export function NotificationSection() {
  return (
    <Card className="border-border-standard bg-surface">
      <CardHeader className="pb-3">
        <CardTitle className="text-base font-medium flex items-center gap-2">
          <Bell className="w-4 h-4 text-brand" weight="fill" />
          알림 설정
          <span className="ml-1 inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-brand/10 border border-brand/30 text-brand tracking-wide">
            준비중
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-text-muted leading-relaxed">
          인허가 변동 감지 시 원하는 채널로 즉시 알림을 받을 수 있습니다.{' '}
        </p>

        <div className="rounded-xl border border-border-standard overflow-hidden divide-y divide-border-standard">
          {NOTIFICATION_CHANNELS.map((ch) => (
            <div
              key={ch.id}
              className="flex items-center justify-between px-5 py-4 bg-surface/30 opacity-60 cursor-not-allowed"
              title="준비중인 기능입니다"
            >
              {/* 채널 정보 */}
              <div className="flex items-center gap-3 min-w-0">
                {ch.icon}
                <div className="min-w-0">
                  <p className="text-sm font-medium text-text-primary">{ch.label}</p>
                  <p className="text-xs text-text-muted mt-0.5 leading-relaxed">{ch.description}</p>
                </div>
              </div>

              {/* 토글 + 준비중 뱃지 */}
              <div className="flex items-center gap-3 shrink-0 ml-4">
                <span className="text-[10px] font-medium text-text-muted/70 border border-border-standard px-2 py-0.5 rounded-full whitespace-nowrap">
                  준비중인 기능입니다
                </span>
                <ToggleLeft className="w-7 h-7 text-text-muted/40" aria-disabled="true" />
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
