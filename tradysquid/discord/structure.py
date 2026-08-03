from __future__ import annotations
class DiscordStructureService:
    def __init__(self,schema:dict): self.schema=schema
    async def sync(self,guild):
        categories={c.name.casefold():c for c in guild.categories}; receipts=[]
        for definition in self.schema.get('categories',[]):
            name=definition['name']; category=categories.get(name.casefold())
            if category is None: category=await guild.create_category(name,reason='Tradysquid declarative structure')
            channels={c.name.casefold():c for c in category.text_channels}
            for channel_name in definition['channels']:
                channel=channels.get(channel_name.casefold())
                if channel is None: channel=await guild.create_text_channel(channel_name,category=category,reason='Tradysquid declarative structure')
                receipts.append({'category':name,'channel':channel_name,'id':str(channel.id)})
        return receipts
