export type StreamEvent<T> = {type:"delta";text:string}|{type:"status";text:string}|{type:"done";data:T}|{type:"error";message:string};
export async function readChatStream<T>(response: Response, onEvent:(event:StreamEvent<T>)=>void){
  if(!response.ok){const d=await response.json().catch(()=>null);throw new Error(typeof d?.detail==="string"?d.detail:`Error del servidor (${response.status})`)}
  if(!response.body)throw new Error("El servidor no devolvió una respuesta");
  const reader=response.body.getReader();const decoder=new TextDecoder();let buffer="";let completed=false;
  try{
    while(true){const {value,done}=await reader.read();buffer+=decoder.decode(value,{stream:!done});let end;
      while((end=buffer.indexOf("\n\n"))>=0){const frame=buffer.slice(0,end);buffer=buffer.slice(end+2);if(!frame.startsWith("data: "))continue;const event=JSON.parse(frame.slice(6)) as StreamEvent<T>;if(event.type==="error")throw new Error(event.message);if(event.type==="done")completed=true;onEvent(event)}
      if(done)break;
    }
    if(!completed)throw new Error("Se interrumpió la respuesta. Puedes reintentar.");
  }finally{await reader.cancel().catch(()=>{});reader.releaseLock()}
}
