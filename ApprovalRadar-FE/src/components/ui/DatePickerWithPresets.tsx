
import { format, startOfWeek, endOfWeek, startOfMonth, endOfMonth, startOfToday } from "date-fns"
import { ko } from "date-fns/locale"
import { Calendar as CalendarIcon } from "lucide-react"

import { cn } from "../../lib/utils"
import { Button } from "./button"
import { Calendar } from "./calendar"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "./popover"

interface DatePickerWithPresetsProps {
  date: { from: Date; to: Date } | undefined;
  setDate: (date: { from: Date; to: Date } | undefined) => void;
}

export function DatePickerWithPresets({ date, setDate }: DatePickerWithPresetsProps) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant={"outline"}
          className={cn(
            "w-[280px] justify-start text-left font-normal bg-background border-border-standard",
            !date && "text-muted-foreground"
          )}
        >
          <CalendarIcon className="mr-2 h-4 w-4" />
          {date?.from ? (
            date.to ? (
              <>
                {format(date.from, "y년 M월 d일", { locale: ko })} -{" "}
                {format(date.to, "y년 M월 d일", { locale: ko })}
              </>
            ) : (
              format(date.from, "y년 M월 d일", { locale: ko })
            )
          ) : (
            <span>기간 선택</span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="flex w-auto p-0" align="start">
        <div className="flex flex-col gap-3 p-4 border-r border-border-standard">
          <Button
            variant="ghost"
            className="justify-start font-normal"
            onClick={() => setDate({ from: startOfToday(), to: startOfToday() })}
          >
            오늘
          </Button>
          <Button
            variant="ghost"
            className="justify-start font-normal"
            onClick={() => setDate({ from: startOfWeek(startOfToday(), { weekStartsOn: 1 }), to: endOfWeek(startOfToday(), { weekStartsOn: 1 }) })}
          >
            이번 주
          </Button>
          <Button
            variant="ghost"
            className="justify-start font-normal"
            onClick={() => setDate({ from: startOfMonth(startOfToday()), to: endOfMonth(startOfToday()) })}
          >
            이번 달
          </Button>
        </div>
        <div className="p-4">
          <Calendar
            mode="range"
            defaultMonth={date?.from}
            selected={{ from: date?.from, to: date?.to }}
            onSelect={(range) => {
              if (range) {
                setDate({ from: range.from as Date, to: range.to || (range.from as Date) });
              } else {
                setDate(undefined);
              }
            }}
            numberOfMonths={1}
            locale={ko}
            captionLayout="dropdown"
            startMonth={new Date(2000, 0)}
            endMonth={new Date(2050, 11)}
          />
        </div>
      </PopoverContent>
    </Popover>
  )
}
