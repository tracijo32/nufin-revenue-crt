### ARD revenue balancer

Author: Traci Johnson

#### Overview
This code automates the process of balancing the wire transfers of revenue from Stripe with the internal accounting provided on ARD's internal Salesforce data warehouse - CatConnect.

Stripe reports the wire transfers every business day at 6:59pm for all the transactions that occured from 7:00pm the previous day. Those wires need to be claimed with the charges, fees, and refunds assigned properly to Northwestern University chart strings for proper accounting.

Revenue for ARD comes in through either events or membership dues (gifts are handled separately). We have reports for both of them. Blackthorn tracks the events, and most importantly, the listed chart strings - and by the look of it is already connected to Stripe. Both contain the transaction ID that can be used to link the lines. The memberships are, unfortunately, not linked to stripe transactions. However, I've managed to find an automatic way to assign the charges based on donor name fuzzy matching with customer ID, the payment date matching to transaction date, and the amounts balanced.

There still remain several manual inputs. Refunds are more complicated - I can match them to a transaction ID, but the refund is usually only part of the transaction total, unless you can determine exactly which line item on the invoice is being refunded (usually, it's the one that has the same amount) or the entire transaction maps to one chart string, then it isn't trivial. Membership subscription updates are also not trivial to link to a chart string - donors can belong to many different clubs.

Also, we can't count on the folks creating these events to properly enter the full chart string. Many of them are only partial. Therefore I added an entry point that allows users to manually update the chart strings that map to events based on the event name and/or item name on the invoice.


### To future developers
I hope that this repo falls into the lap of a data scientist who can greatly improve this process from what I've started. This was a solution that was generated within only a few weeks given with access to only exported reports delivered as flat files. If given a few months, I would have looked into getting developer-level permissions set so I could access data directly from Salesforce and/or Stripe through the API (based on what I've seen, I think they are already connected to each other, so you may only need SF). 

As much as I wanted to make this code more sophisticated, I had to deliver code that was simple yet robust - where modifications could be made through reading manually-updated flat files and not more lines of code. There is 100% a solution to this process that can be entirely written in SQL on a Salesforce.

Nevertheless, I will try to document this code as best I can so that you can use the logic to get started on a better solution. Good luck!

You probably already know this, but if you plan on forking this repo, be sure not to include any sensitive information. Do not commit any files with actual donor names, transations, chart strings, etc. Avoid hard coding any of these values - pass them in as parameters using the configuration file.
