#include <generated/csr.h>
#include <irq.h>
#include <uart.h>

#include "dvisampler.h"

void isr(void);
void isr(void)
{
	unsigned int irqs;

	irqs = irq_pending() & irq_getmask();

	if(irqs & (1 << UART_INTERRUPT))
		uart_isr();
	if(irqs & (1 << DVISAMPLER_INTERRUPT))
		dvisampler_isr();
}
